"""QuantRadar FastAPI 服务骨架（Phase 7）。

仅暴露真实能力，所有价格/回测均来自 InvestmentDataProvider（investment_data），禁止 mock。
接口：
    GET  /api/health            健康检查 + provider 状态
    GET  /api/price             透传 provider.get_price（真实行情）
    POST /api/backtest          运行真实回测，返回 summary + 结果快照（可复现指纹）
    POST /api/snapshot/save     保存快照 JSON
    GET  /api/snapshot/load     读取快照 JSON
"""

from __future__ import annotations

import os
import tempfile
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

_SNAPSHOT_DIR = os.environ.get(
    "QUANT_RADAR_SNAPSHOT_DIR",
    os.path.join(tempfile.gettempdir(), "quantradar_snapshots"),
)


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
