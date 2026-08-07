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

from quantradar.bootstrap import bootstrap_investment_data
from quantradar.snapshot import build_snapshot, load_snapshot, save_snapshot

app = FastAPI(title="QuantRadar API", version="0.1.0")

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
    prov = _ensure_provider()
    return {"status": "ok", "provider": getattr(prov, "name", None)}


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


@app.post("/api/backtest")
def backtest(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    from bullet_trade.core.engine import BacktestEngine

    _ensure_provider()
    security = payload["security"]
    start = payload.get("start_date")
    end = payload.get("end_date")
    initial_cash = float(payload.get("initial_cash", 500000))
    frequency = payload.get("frequency", "day")
    amount = int(payload.get("amount", 100))

    state = {"bought": False}

    def _init(context):  # noqa: ANN001
        state["bought"] = False

    def _handle(context, data):  # noqa: ANN001
        df = get_price(security, count=5, fields=["close"])
        if df is None or df.empty:
            return
        if not state["bought"]:
            order_target(security, amount)
            state["bought"] = True

    engine = BacktestEngine(
        initialize=_init,
        handle_data=_handle,
        start_date=start,
        end_date=end,
        frequency=frequency,
        initial_cash=initial_cash,
    )
    engine.run()
    if not engine.daily_records:
        raise HTTPException(status_code=422, detail="回测未产出任何记录（检查区间/数据）")
    snap = build_snapshot(engine, extras=payload.get("extras"))
    summary = {
        "security": security,
        "start_date": start,
        "end_date": end,
        "initial_cash": initial_cash,
        "frequency": frequency,
        "records_count": len(engine.daily_records),
        "final_total_value": engine.daily_records[-1].get("total_value"),
    }
    return {"summary": summary, "snapshot": snap}


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
