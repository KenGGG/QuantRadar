"""QuantRadar FastAPI 服务骨架（Phase 7）。

仅暴露真实能力，所有价格/回测均来自 InvestmentDataProvider（investment_data），禁止 mock。
接口：
    GET  /api/health            健康检查 + provider 状态（含最新数据日期）
    GET  /api/price             透传 provider.get_price（真实行情）
    POST /api/data/pull         在本地 Dolt 仓库执行 dolt pull 更新数据
    POST /api/backtest          运行真实回测，返回 summary + 结果快照（可复现指纹）
    POST /api/snapshot/save     保存快照 JSON
    GET  /api/snapshot/load     读取快照 JSON
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from datetime import date
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from quantradar.backtest import run_backtest
from quantradar.bootstrap import bootstrap_investment_data
from quantradar.snapshot import build_snapshot, load_snapshot, save_snapshot
from quantradar.worker import get_worker

app = FastAPI(title="QuantRadar API", version="0.1.0")

_HTML_PATH = os.path.join(os.path.dirname(__file__), "static", "index.html")
# 生产构建产物优先：若 frontend/dist/index.html 存在则托管之（React+TS+Vite）。
_DIST_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "frontend", "dist", "index.html")
)
_DIST_DIR = os.path.dirname(_DIST_PATH)
_ASSETS_DIR = os.path.join(_DIST_DIR, "assets")

# investment_data 的本地 Dolt 仓库目录（dolt pull 在此执行）；可用环境变量覆盖。
_DOLT_REPO_DIR = os.environ.get("QUANTRADAR_DOLT_REPO", "/data/investment_data")

_SNAPSHOT_DIR = os.environ.get(
    "QUANT_RADAR_SNAPSHOT_DIR",
    os.path.join(tempfile.gettempdir(), "quantradar_snapshots"),
)


def _research_store():
    from quantradar.research.config import ResearchSettings
    from quantradar.research.storage import ResearchStore
    return ResearchStore(ResearchSettings.from_env())


@app.get("/api/research/dates")
def research_dates() -> Dict[str, Any]:
    """List collected Research dates, newest first; no artifact paths are exposed."""
    try:
        return {"dates": [value.isoformat() for value in _research_store().list_dates()]}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Research storage unavailable: {exc}")


@app.get("/api/research/reports")
def research_reports(
    target_date: date = Query(..., alias="date"),
    channel: str = Query(..., pattern="^(HOT|STRATEGY|FINANCIAL_ENGINEERING)$"),
) -> Dict[str, Any]:
    """Return presentation-safe report metadata for a collected channel."""
    try:
        reports = _research_store().list_channel_reports(target_date, channel)
        for report in reports:
            report["publish_date"] = report["publish_date"].isoformat()
        return {"reports": reports}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Research storage unavailable: {exc}")


@app.get("/api/research/status")
def research_status(target_date: date = Query(..., alias="date")) -> Dict[str, Any]:
    try:
        counts = _research_store().channel_counts(target_date)
        return {
            "date": target_date.isoformat(),
            "channels": {channel: counts.get(channel, 0) for channel in ("HOT", "STRATEGY", "FINANCIAL_ENGINEERING")},
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Research storage unavailable: {exc}")


def _ensure_provider():
    """惰性确保全局 active provider 为 InvestmentDataProvider（只读真实数据）。"""
    from bullet_trade.data import get_data_provider

    from quantradar.providers.investment_data.provider import InvestmentDataProvider

    prov = get_data_provider()
    if not isinstance(prov, InvestmentDataProvider):
        bootstrap_investment_data(set_active=True, overwrite=True)
    return get_data_provider()


def _row_to_record(idx, row, columns) -> Dict[str, Any]:
    rec = {"date": pd.Timestamp(idx).strftime("%Y-%m-%d")}
    for col in columns:
        v = row[col]
        rec[col] = None if (v is None or (isinstance(v, float) and v != v)) else float(v)
    return rec


@app.get("/api/health")
def health() -> Dict[str, Any]:
    from quantradar.audit import collect_audit_env

    prov = _ensure_provider()
    return {
        "status": "ok",
        "provider": getattr(prov, "name", None),
        "environment": collect_audit_env(),
    }


@app.post("/api/data/pull")
def pull_data() -> Dict[str, Any]:
    """更新 investment_data：在本地 Dolt 仓库目录执行 `dolt pull`（拉取 origin 最新数据）。

    仅拉取，不做 merge/commit 等额外写操作；失败时将 dolt 输出原样返回前端。
    目录默认 /data/investment_data，可用 QUANTRADAR_DOLT_REPO 覆盖。
    """
    from quantradar.audit import collect_audit_env

    try:
        proc = subprocess.run(
            ["dolt", "pull"],
            cwd=_DOLT_REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        ok = proc.returncode == 0
        message = (proc.stdout + proc.stderr).strip() or ("dolt pull 成功" if ok else "dolt pull 失败")
        result: Dict[str, Any] = {
            "ok": ok,
            "returncode": proc.returncode,
            "message": message[-2000:],
        }
        if ok:
            # 拉取成功后刷新审计环境（最新数据日期/dolt_commit 同步）
            try:
                prov = _ensure_provider()
                result["environment"] = collect_audit_env()
            except Exception:
                pass
        return result
    except FileNotFoundError:
        return {"ok": False, "returncode": -1, "message": f"未找到 dolt 命令（仓库目录：{_DOLT_REPO_DIR}）"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "returncode": -1, "message": "dolt pull 超时（>600s）"}
    except Exception as e:  # noqa: BLE001 - 将任意异常透传给前端
        return {"ok": False, "returncode": -1, "message": str(e)}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    """中文 WebUI 单页（消费 /api/*，不直连数据库）。优先托管构建产物 dist，回退到静态页。"""
    target = _DIST_PATH if os.path.exists(_DIST_PATH) else _HTML_PATH
    if not os.path.exists(target):
        raise HTTPException(status_code=404, detail="前端页面缺失")
    with open(target, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/price")
def price(
    security: str = Query(..., description="JoinQuant 代码，如 600519.XSHG"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    fq: str = Query("none"),
    fields: Optional[str] = Query(None, description="逗号分隔字段"),
    count: Optional[int] = Query(None),
) -> Dict[str, Any]:
    prov = _ensure_provider()
    field_list = [f.strip() for f in fields.split(",")] if fields else None
    df = prov.get_price(
        security, start_date, end_date, fq=fq, fields=field_list, count=count
    )
    if df is None or df.empty:
        return {"security": security, "rows": []}
    rows = [_row_to_record(idx, row, df.columns) for idx, row in df.iterrows()]
    return {"security": security, "rows": rows}


def _summary_from(engine, snapshot, *, security=None, strategy="builtin"):
    return {
        "strategy": strategy,
        "security": security,
        "start_date": snapshot["config"]["start_date"],
        "end_date": snapshot["config"]["end_date"],
        "initial_cash": snapshot["config"]["initial_cash"],
        "frequency": snapshot["config"]["frequency"],
        "records_count": snapshot["records_count"],
        "trades_count": len(getattr(engine, "trades", []) or []),
        "final_total_value": snapshot["metrics"].get("final_total_value"),
    }


@app.post("/api/backtest")
def backtest(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    _ensure_provider()
    security = payload["security"]
    engine, snap = run_backtest(
        code=None,
        security=security,
        start_date=payload.get("start_date"),
        end_date=payload.get("end_date"),
        initial_cash=float(payload.get("initial_cash", 500000)),
        frequency=payload.get("frequency", "day"),
        amount=int(payload.get("amount", 100)),
        extras=payload.get("extras"),
    )
    if not engine.daily_records:
        raise HTTPException(status_code=422, detail="回测未产出任何记录（检查区间/数据）")
    return {"summary": _summary_from(engine, snap, security=security), "snapshot": snap}


@app.post("/api/backtest/strategy")
def backtest_strategy(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """运行用户提交的策略源码（JoinQuant 兼容：get_price/order_target/log/g/run_daily 等由引擎注入）。

    仅接受策略源码字符串；引擎以文件方式加载并注入 BulletTrade 全局命名空间，复用其撮合/账户/
    订单/成交/调度/佣金/滑点等能力，禁止重新实现。本接口为本地可信研究工具，不在本环境做沙箱隔离。
    """
    _ensure_provider()
    code = payload.get("code")
    if not code or not isinstance(code, str):
        raise HTTPException(status_code=400, detail="缺少 strategy code")
    engine, snap = run_backtest(
        code=code,
        start_date=payload.get("start_date"),
        end_date=payload.get("end_date"),
        initial_cash=float(payload.get("initial_cash", 500000)),
        frequency=payload.get("frequency", "day"),
        extras=payload.get("extras"),
    )
    if not engine.daily_records:
        raise HTTPException(status_code=422, detail="回测未产出任何记录（检查区间/数据/策略）")
    return {"summary": _summary_from(engine, snap, strategy="user-submitted"), "snapshot": snap}


# ---------------------- 异步回测（Worker + PostgreSQL） ----------------------


@app.post("/api/backtest/async")
def backtest_async(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """提交异步回测：立即返回 run_id + PENDING，后台 Worker 执行并落库 PostgreSQL。

    复用 quantradar.worker.submit（内部复用 run_backtest -> BulletTrade）。
    未配置 QUANT_RADAR_PG_URL 时返回 503（不硬编码凭证）。
    """
    try:
        return get_worker().submit(
            payload={
                "code": payload.get("code"),
                "security": payload.get("security"),
                "start_date": payload.get("start_date"),
                "end_date": payload.get("end_date"),
                "initial_cash": float(payload.get("initial_cash", 500000)),
                "frequency": payload.get("frequency", "day"),
                "amount": int(payload.get("amount", 100)),
                "benchmark": payload.get("benchmark"),
                "fq": payload.get("fq", "none"),
                "strategy_name": payload.get("strategy_name"),
                "extras": payload.get("extras"),
            }
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/api/backtest/runs/{run_id}")
def backtest_run_status(run_id: str) -> Dict[str, Any]:
    """查询运行结果：PENDING/RUNNING/SUCCESS/FAILED + 落库快照/指标。"""
    rec = get_worker().get_status(run_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"运行不存在：{run_id}")
    return rec


@app.get("/api/backtest/runs")
def backtest_runs_list(limit: int = Query(50, ge=1, le=500)) -> Dict[str, Any]:
    """列出近期运行（按创建时间倒序）。"""
    from quantradar.storage import list_runs

    try:
        return {"runs": list_runs(limit)}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


# ---------------------- 报告 Artifact 服务（直接复用 BulletTrade HTML） ----------------------


def _run_dir_of(run_id: str) -> str:
    """从运行记录取产物目录；记录不存在或缺失目录则抛 404。"""
    rec = get_worker().get_status(run_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"运行不存在：{run_id}")
    run_dir = (rec.get("config") or {}).get("run_dir")
    if not run_dir or not os.path.isdir(run_dir):
        raise HTTPException(status_code=404, detail=f"运行产物目录缺失：{run_id}")
    return run_dir


@app.get("/api/backtest/runs/{run_id}/report")
def backtest_run_report(run_id: str, which: str = Query("full", pattern="^(full|standard)$")):
    """直接返回该次 BulletTrade 原生 HTML 报告（前端 iframe 嵌入，禁止前端重算指标）。

    - which=full（默认）：report.html（详细交互报告：指标+曲线+月度热力图+Trades/Positions/Daily 表）。
    - which=standard：standard_report.html（聚宽风格精简报告，generate_cli_report 产出）。
    """
    run_dir = _run_dir_of(run_id)
    fname = "report.html" if which == "full" else "standard_report.html"
    path = os.path.join(run_dir, fname)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"报告文件不存在：{fname}（运行可能尚未成功或生成失败）")
    return FileResponse(
        path,
        media_type="text/html",
        filename=fname,
        content_disposition_type="inline",  # 浏览器内联展示（ReportPage iframe 直接渲染，不当附件下载）
    )


@app.get("/api/backtest/runs/{run_id}/artifacts")
def backtest_run_artifacts(run_id: str) -> Dict[str, Any]:
    """列出该次运行产物目录内可用的报告/CSV/日志/图片清单（不含大文件内容，仅元数据）。"""
    run_dir = _run_dir_of(run_id)
    items = []
    for root, dirs, files in os.walk(run_dir):
        if "__pycache__" in root:
            continue
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in sorted(files):
            full = os.path.join(root, name)
            rel = os.path.relpath(full, run_dir)
            try:
                size = os.path.getsize(full)
            except OSError:
                size = None
            ext = os.path.splitext(name)[1].lower().lstrip(".")
            items.append(
                {
                    "name": rel,
                    "size": size,
                    "ext": ext,
                    "is_report": name in ("report.html", "standard_report.html"),
                }
            )
    return {
        "run_id": run_id,
        "run_dir": run_dir,
        "artifacts": items,
        "report_url": f"/api/backtest/runs/{run_id}/report?which=full",
        "standard_report_url": f"/api/backtest/runs/{run_id}/report?which=standard",
    }


# 常见产物扩展名 -> media type（供查看/下载时正确渲染）
_MEDIA_BY_EXT = {
    "html": "text/html",
    "htm": "text/html",
    "csv": "text/csv",
    "json": "application/json",
    "log": "text/plain",
    "txt": "text/plain",
    "md": "text/markdown",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "svg": "image/svg+xml",
    "gif": "image/gif",
    "js": "application/javascript",
    "css": "text/css",
}


@app.get("/api/backtest/runs/{run_id}/artifacts/{name:path}")
def backtest_run_artifact_file(run_id: str, name: str):
    """查看 / 下载单次运行的产物文件（CSV / 日志 / 图片 / HTML / JSON 等）。

    - 路径限定在 runs/<run_id>/ 目录内（规范化后校验前缀，防目录穿越）。
    - 按扩展名推断 Content-Type；浏览器据 Content-Disposition 决定内联或下载。
    """
    run_dir = _run_dir_of(run_id)
    norm_dir = os.path.normpath(run_dir)
    full = os.path.normpath(os.path.join(run_dir, name))
    if full != norm_dir and not full.startswith(norm_dir + os.sep):
        raise HTTPException(status_code=400, detail="非法产物路径（禁止目录穿越）")
    if not os.path.isfile(full):
        raise HTTPException(status_code=404, detail=f"产物文件不存在：{name}")
    ext = os.path.splitext(name)[1].lower().lstrip(".")
    media = _MEDIA_BY_EXT.get(ext, "application/octet-stream")
    return FileResponse(full, media_type=media, filename=os.path.basename(full))


@app.get("/api/experiments")
def experiments_list() -> Dict[str, Any]:
    from quantradar.experiment import list_experiments

    return {"experiments": list_experiments()}


@app.get("/api/experiments/{name}")
def experiments_load(name: str) -> Dict[str, Any]:
    from quantradar.experiment import load_experiment

    try:
        exp = load_experiment(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Experiment 不存在：{name}")
    return exp.to_dict()


@app.post("/api/experiments/save")
def experiments_save(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    from quantradar.experiment import Experiment, save_experiment

    name = payload.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="缺少 name")
    snap = payload.get("snapshot") or {}
    exp = Experiment(
        name=name,
        kind=payload.get("kind", "backtest"),
        config=payload.get("config", {}),
        result_fingerprint=snap.get("result_fingerprint", "") or payload.get("result_fingerprint", ""),
        metrics=payload.get("metrics", {}),
        snapshot=snap or None,
    )
    path = save_experiment(exp)
    return {"path": path, "name": name}


@app.post("/api/snapshot/save")
def snapshot_save(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    snapshot = payload.get("snapshot")
    if snapshot is None:
        raise HTTPException(status_code=400, detail="缺少 snapshot 字段")
    name = payload.get("name") or snapshot.get("result_fingerprint", "snapshot")
    path = os.path.join(_SNAPSHOT_DIR, f"{name}.json")
    save_snapshot(snapshot, path)
    return {"path": path}


@app.get("/api/snapshot/load")
def snapshot_load(path: str = Query(...)) -> Dict[str, Any]:
    if not os.path.isabs(path):
        path = os.path.join(_SNAPSHOT_DIR, os.path.basename(path))
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"快照不存在：{path}")
    return load_snapshot(path)


# ---------------------------------------------------------------------------
# 前端静态资源挂载与 SPA 客户端路由兜底
# ---------------------------------------------------------------------------
# React+TS+Vite 构建产物（frontend/dist）的入口 index.html 以绝对路径
# /assets/*.js|css 引用资源，必须由后端挂载 /assets 才能加载，否则白屏。
if os.path.isdir(_ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=_ASSETS_DIR), name="assets")


@app.get("/{full_path:path}")
def spa_fallback(full_path: str) -> Any:
    """SPA 客户端路由兜底：非 API、非静态资源的页面路由返回 index.html。

    带文件扩展名的请求（favicon.ico、*.map 等）按 404 处理，避免吞成 HTML。
    """
    if not os.path.exists(_DIST_PATH):
        raise HTTPException(status_code=404, detail="前端页面缺失")
    if os.path.splitext(full_path)[1]:
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(_DIST_PATH)


# ---------------------------------------------------------------------------
# 启动事件：幂等建表（避免首次访问 /api/backtest/runs 时表尚不存在而 500）
# ---------------------------------------------------------------------------
@app.on_event("startup")
def _startup_init_pg() -> None:
    """应用启动时确保 PostgreSQL 表就绪；未配置 QUANT_RADAR_PG_URL 时跳过（相关接口仍 503）。"""
    import sys

    if os.environ.get("QUANT_RADAR_PG_URL"):
        try:
            from quantradar.storage import init_db

            init_db()
            print("[QuantRadar] PostgreSQL 表已就绪（异步回测可用）")
        except Exception as exc:  # noqa: BLE001
            print(
                f"[QuantRadar] 警告：PostgreSQL 初始化失败，异步回测将不可用：{exc}",
                file=sys.stderr,
            )
