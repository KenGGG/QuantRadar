"""Phase 8/STOCK_V1：浏览器策略回测端点（用户源码 → BulletTrade 真实回测）。

验证 /api/backtest/strategy 接受 JoinQuant 兼容的用户策略源码，经 InvestmentDataProvider
跑真实数据，返回 summary(trades_count) 与可复现快照。无 mock。
"""

from __future__ import annotations

import pytest

from fastapi.testclient import TestClient

pytestmark = pytest.mark.requires_dolt

from quantradar.api.app import app

SECURITY = "600519.XSHG"
START = "2023-01-01"
END = "2023-03-31"
CASH = 500000

BUY_HOLD = (
    "def initialize(context):\n"
    "    context.security = '600519.XSHG'\n"
    "    context.amount = 100\n"
    "def handle_data(context, data):\n"
    "    if not context.portfolio.positions:\n"
    "        order_target(context.security, context.amount)\n"
)


def test_strategy_endpoint_runs_real_backtest():
    client = TestClient(app)
    r = client.post(
        "/api/backtest/strategy",
        json={"code": BUY_HOLD, "start_date": START, "end_date": END, "initial_cash": CASH},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"]["trades_count"] >= 1, "用户策略未产生成交"
    assert "snapshot" in body and body["snapshot"].get("result_fingerprint")
    assert body["summary"]["final_total_value"] is not None


def test_strategy_endpoint_rejects_empty_code():
    client = TestClient(app)
    r = client.post("/api/backtest/strategy", json={"code": ""})
    assert r.status_code == 400


def test_experiments_list_and_save_roundtrip():
    client = TestClient(app)
    # 先跑一个策略并保存为实验
    r = client.post(
        "/api/backtest/strategy",
        json={"code": BUY_HOLD, "start_date": START, "end_date": END, "initial_cash": CASH},
    )
    assert r.status_code == 200
    snap = r.json()["snapshot"]
    name = snap["result_fingerprint"]
    r = client.post(
        "/api/experiments/save",
        json={"name": name, "kind": "backtest", "config": snap.get("config", {}), "snapshot": snap},
    )
    assert r.status_code == 200 and r.json().get("name") == name
    # 列表可见
    r = client.get("/api/experiments")
    assert r.status_code == 200 and name in r.json()["experiments"]
    # 加载可见指纹
    r = client.get(f"/api/experiments/{name}")
    assert r.status_code == 200 and r.json()["result_fingerprint"] == name
