"""异步回测 Worker（Hardening#57：固定线程池 + 重启恢复）。

职责：
  - submit：生成 run_id，落库 PENDING 运行（策略源码先落库 strategies 表并绑定 strategy_id），
    提交到固定大小线程池执行真实回测。
  - _run：调用 quantradar.backtest.run_backtest（复用 BulletTrade 撮合/账户/订单，禁止重实现），
    回测完成写 Snapshot/Metrics/结果快照，更新状态 RUNNING→SUCCESS/FAILED。
  - recover：进程重启后将遗留的 RUNNING/PENDING 运行恢复为 PENDING 并重新入队（单进程内保证最多一次重试）。
  - get_status / get_result：查询运行状态与结果。

线程模型（本地可信研究工具）：
  - 固定大小 ThreadPoolExecutor（默认 4 线程），杜绝「每次提交新建线程无限增长」。
  - 单 uvicorn 进程内运行；多进程水平扩展不在本地研究工具范围（单进程已足够，FOR UPDATE
    SKIP LOCKED 的分布式锁亦非必需）。
"""

from __future__ import annotations

import concurrent.futures
import datetime
import hashlib
import os
import threading
import traceback
import uuid
from typing import Any, Dict, Optional

from .storage import (
    create_run,
    get_run,
    get_strategy,
    list_runs_by_status,
    save_metrics,
    save_snapshot_record,
    save_strategy,
    update_run,
)
from .backtest_run import default_runs_dir, run_unified_backtest

# 固定线程池大小（本地研究工具，单进程即可；避免无限线程）。
WORKER_POOL_SIZE = 4

_executor: Optional[concurrent.futures.ThreadPoolExecutor] = None
_executor_lock = threading.Lock()


def _get_executor() -> concurrent.futures.ThreadPoolExecutor:
    global _executor
    if _executor is None:
        with _executor_lock:
            if _executor is None:
                _executor = concurrent.futures.ThreadPoolExecutor(
                    max_workers=WORKER_POOL_SIZE, thread_name_prefix="qr_worker"
                )
    return _executor


def _hash_source(code: str) -> str:
    """策略源码的稳定哈希（sha256），用于审计链与去重。"""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _now() -> datetime.datetime:
    return datetime.datetime.now()


def _gen_run_id() -> str:
    return "run_" + uuid.uuid4().hex


def _payload_from_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """从落库运行记录重建回测 payload（用于重启恢复）。"""
    cfg = rec.get("config") or {}
    code = None
    sid = rec.get("strategy_id")
    if sid is not None:
        try:
            s = get_strategy(sid)
            code = s.source if s is not None else None
        except Exception:
            code = None
    return {
        "code": code,
        "security": cfg.get("security"),
        "start_date": cfg.get("start_date"),
        "end_date": cfg.get("end_date"),
        "initial_cash": cfg.get("initial_cash", 500000),
        "frequency": cfg.get("frequency", "day"),
        "amount": cfg.get("amount", 100),
        "benchmark": cfg.get("benchmark"),
        "fq": cfg.get("fq", "none"),
        "strategy_name": cfg.get("strategy_name"),
        "extras": cfg.get("extras"),
    }


class BacktestWorker:
    """把「提交 → 运行 → 落库」封装为本地线程池 Worker。"""

    def __init__(self) -> None:
        self._futures: Dict[str, concurrent.futures.Future] = {}
        self._lock = threading.Lock()
        self._recovered = False

    # ----------------------------- 提交 -----------------------------
    def submit(self, payload: Dict[str, Any], strategy_id: Optional[int] = None) -> Dict[str, Any]:
        """提交一次异步回测，立即返回 run_id（状态 PENDING）。

        会惰性建表（init_db）；若 QUANT_RADAR_PG_URL 未配置则抛 RuntimeError，由 API 转 503。
        审计链：用户策略源码先落库 strategies 表，运行绑定 strategy_id。
        """
        from .storage import init_db

        init_db()
        run_id = _gen_run_id()

        # 审计链：用户策略源码持久化到 strategies 表，回测运行绑定 strategy_id。
        code = payload.get("code")
        if strategy_id is None and code:
            strategy_id = save_strategy(
                name=payload.get("strategy_name") or "user_strategy",
                source=code,
                strategy_hash=_hash_source(code),
            ).id

        config = {
            "security": payload.get("security"),
            "start_date": payload.get("start_date"),
            "end_date": payload.get("end_date"),
            "initial_cash": payload.get("initial_cash", 500000),
            "frequency": payload.get("frequency", "day"),
            "amount": payload.get("amount", 100),
            "benchmark": payload.get("benchmark"),
            "fq": payload.get("fq", "none"),
            "extras": payload.get("extras"),
            "has_code": bool(code),
            "strategy_name": payload.get("strategy_name"),
            "strategy_id": strategy_id,
            "strategy_hash": _hash_source(code) if code else None,
            # 产物目录与报告路径（供 /runs/{id}/report 与 /artifacts 定位文件，不入数据库大文件）
            "run_dir": os.path.join(default_runs_dir(), run_id),
            "report_html": os.path.join(default_runs_dir(), run_id, "report.html"),
            "standard_report_html": os.path.join(default_runs_dir(), run_id, "standard_report.html"),
            "strategy_source": code,
        }
        create_run(run_id, config, strategy_id=strategy_id)
        self._enqueue(run_id, payload)
        return {"run_id": run_id, "status": "PENDING", "config": config}

    def _enqueue(self, run_id: str, payload: Dict[str, Any]) -> None:
        """提交到固定线程池执行（bounded；不会无限增长线程）。"""
        future = _get_executor().submit(self._run, run_id, payload)
        with self._lock:
            self._futures[run_id] = future

    # ----------------------------- 执行 -----------------------------
    def _run(self, run_id: str, payload: Dict[str, Any]) -> None:
        try:
            update_run(run_id, status="RUNNING", started_at=_now())
            # 统一回测链：create_backtest → generate_report → generate_cli_report，
            # 产物写入 runs/<run_id>/（report.html / standard_report.html / metrics.json / CSV / 日志 / snapshot.json）。
            # 复用 BulletTrade 原生指标与报告，禁止重实现。
            info = run_unified_backtest(run_id, payload)
            # 持久化：Snapshot manifest（附加审计）+ 完整 BulletTrade metrics + 运行结果
            # （顺序保证结果先于状态 SUCCESS）
            save_snapshot_record(
                info["snapshot"]["snapshot_id"], run_id, info["snapshot"], info["result_hash"]
            )
            save_metrics(run_id, info["metrics"])
            update_run(
                run_id,
                status="SUCCESS",
                finished_at=_now(),
                result_hash=info["result_hash"],
                snapshot=info["snapshot"],
                metrics=info["metrics"],
            )
        except Exception as exc:  # noqa: BLE001 -- 全捕获以落库失败原因
            update_run(
                run_id,
                status="FAILED",
                finished_at=_now(),
                error="".join(traceback.format_exception_only(type(exc), exc))[:4000],
            )
        finally:
            with self._lock:
                self._futures.pop(run_id, None)

    # ----------------------------- 重启恢复 -----------------------------
    def recover(self) -> int:
        """进程重启后将遗留 RUNNING/PENDING 恢复为 PENDING 并重新入队；返回恢复的运行数。

        覆盖两类遗留任务：
          - RUNNING：进程中途崩溃，回测线程已中断未真正完成。
          - PENDING：已落库但尚未出队执行（如崩溃发生在出队前，或线程池尚未调度）。
        两者都必须在重启后找回重跑，否则会永久卡在 RUNNING/PENDING。

        时序关键：只有 DB 扫描成功才开始才置 _recovered=True。若 PostgreSQL 暂不可用导致
        扫描失败，则不置标志、返回 0，允许后续 get_worker() 再次触发重试——绝不能因一次
        瞬时 DB 故障永久阻断未来的重启恢复。
        """
        if self._recovered:
            return 0
        try:
            pending = list_runs_by_status(["RUNNING", "PENDING"])
        except Exception:
            # PostgreSQL 暂不可用：本次不置 _recovered，允许未来恢复重试
            return 0
        # 扫描成功启动后才标记已恢复，避免 DB 不可用永久阻断后续恢复
        self._recovered = True
        recovered = 0
        for rec in pending:
            rid = rec["run_id"]
            try:
                payload = _payload_from_record(rec)
                update_run(
                    rid,
                    status="PENDING",
                    started_at=None,
                    finished_at=None,
                    error="由进程重启恢复为 PENDING 并重试",
                )
                self._enqueue(rid, payload)
                recovered += 1
            except Exception:
                # 恢复失败不应阻断其它运行；标记为 FAILED 以显式可见
                try:
                    update_run(rid, status="FAILED", error="重启恢复失败")
                except Exception:
                    pass
        return recovered

    # ----------------------------- 查询 -----------------------------
    def get_status(self, run_id: str) -> Optional[Dict[str, Any]]:
        return get_run(run_id)

    def wait(self, run_id: str, timeout: float = 300.0) -> None:
        """等待某次运行完成（测试/同步查询用）。"""
        future: Optional[concurrent.futures.Future] = None
        with self._lock:
            future = self._futures.get(run_id)
        if future is not None:
            try:
                future.result(timeout)
            except Exception:
                # 任务异常已落库 FAILED，这里不向上抛
                pass


# 模块级单例（本地进程内 Worker；不跨进程）。
_worker: Optional[BacktestWorker] = None
_worker_lock = threading.Lock()


def get_worker() -> BacktestWorker:
    global _worker
    if _worker is None:
        with _worker_lock:
            if _worker is None:
                _worker = BacktestWorker()
                _worker.recover()
    return _worker


__all__ = ["BacktestWorker", "get_worker", "WORKER_POOL_SIZE"]
