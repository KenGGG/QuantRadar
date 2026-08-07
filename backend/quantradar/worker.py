"""异步回测 Worker（Closing Phase 2：PERSIST_WORKER_PASS）。

职责：
  - submit：生成 run_id，在 PostgreSQL 落库 PENDING 运行，启动后台线程执行真实回测。
  - _run：调用 quantradar.backtest.run_backtest（复用 BulletTrade 撮合/账户/订单，
          禁止重实现），回测完成写 Snapshot/Metrics/结果快照，更新状态 RUNNING→SUCCESS/FAILED。
  - get_status / get_result：查询运行状态与结果。

线程模型（本地可信研究工具）：以守护线程执行，避免阻塞 API；不引入额外进程/消息队列。
所有价格/撮合/账户均来自 BulletTrade + InvestmentDataProvider，与同步接口共用 run_backtest。
"""

from __future__ import annotations

import datetime
import threading
import traceback
import uuid
from typing import Any, Dict, Optional

from .storage import (
    create_run,
    get_run,
    save_metrics,
    save_snapshot_record,
    update_run,
)


def _now() -> datetime.datetime:
    return datetime.datetime.now()


def _gen_run_id() -> str:
    return "run_" + uuid.uuid4().hex


class BacktestWorker:
    """把「提交 → 运行 → 落库」封装为本地线程 Worker。"""

    def __init__(self) -> None:
        self._threads: Dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    def submit(self, payload: Dict[str, Any], strategy_id: Optional[int] = None) -> str:
        """提交一次异步回测，立即返回 run_id（状态 PENDING）。

        会惰性建表（init_db）；若 QUANT_RADAR_PG_URL 未配置则抛 RuntimeError，由 API 转 503。
        """
        from .storage import init_db

        init_db()
        run_id = _gen_run_id()
        config = {
            "security": payload.get("security"),
            "start_date": payload.get("start_date"),
            "end_date": payload.get("end_date"),
            "initial_cash": payload.get("initial_cash", 500000),
            "frequency": payload.get("frequency", "day"),
            "amount": payload.get("amount", 100),
            "extras": payload.get("extras"),
            "has_code": bool(payload.get("code")),
            "strategy_name": payload.get("strategy_name"),
        }
        create_run(run_id, config, strategy_id=strategy_id)
        t = threading.Thread(target=self._run, args=(run_id, payload), daemon=True)
        with self._lock:
            self._threads[run_id] = t
        t.start()
        return run_id

    def _run(self, run_id: str, payload: Dict[str, Any]) -> None:
        try:
            update_run(run_id, status="RUNNING", started_at=_now())
            from .backtest import run_backtest

            engine, snap = run_backtest(
                code=payload.get("code"),
                security=payload.get("security"),
                start_date=payload.get("start_date"),
                end_date=payload.get("end_date"),
                initial_cash=float(payload.get("initial_cash", 500000)),
                frequency=payload.get("frequency", "day"),
                amount=int(payload.get("amount", 100)),
                extras=payload.get("extras"),
            )
            if not getattr(engine, "daily_records", None):
                raise ValueError("回测未产出任何记录（检查区间/数据/策略）")
            # 持久化：Snapshot manifest + Metrics + 运行结果
            save_snapshot_record(
                snap["snapshot_id"], run_id, snap, snap.get("result_hash")
            )
            save_metrics(run_id, snap.get("metrics") or {})
            update_run(
                run_id,
                status="SUCCESS",
                finished_at=_now(),
                result_hash=snap.get("result_hash"),
                snapshot=snap,
                metrics=snap.get("metrics"),
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
                self._threads.pop(run_id, None)

    def get_status(self, run_id: str) -> Optional[Dict[str, Any]]:
        return get_run(run_id)

    def wait(self, run_id: str, timeout: float = 300.0) -> None:
        """等待某次运行的后台线程结束（测试/同步查询用）。"""
        t: Optional[threading.Thread] = None
        with self._lock:
            t = self._threads.get(run_id)
        if t is not None:
            t.join(timeout)


# 模块级单例（本地进程内 Worker；不跨进程）。
_worker: Optional[BacktestWorker] = None


def get_worker() -> BacktestWorker:
    global _worker
    if _worker is None:
        _worker = BacktestWorker()
    return _worker


__all__ = ["BacktestWorker", "get_worker"]
