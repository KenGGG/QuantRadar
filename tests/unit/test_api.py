"""Phase 7 —— FastAPI 服务基础测试（DB-backed，用 fastapi.testclient）。

覆盖：
    - /api/health 返回 200 且 provider 为 investment_data
    - /api/price 透传真实行情，与原表抽样对账
    - /api/backtest 运行真实回测，返回 summary + 可复现 fingerprint（两次同请求一致）
    - /api/snapshot save/load round-trip

禁止 mock；所有数据来自真实 investment_data。
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.requires_dolt
from fastapi.testclient import TestClient

from quantradar.api.app import app
from quantradar.bootstrap import bootstrap_investment_data
from quantradar.config import load_investment_data_config
from quantradar.providers.investment_data.provider import InvestmentDataProvider

TEST_SECURITY = "600519.XSHG"
START = "2023-01-03"
END = "2023-03-31"


@pytest.fixture(scope="module")
def client():
    bootstrap_investment_data(set_active=True, overwrite=True)
    return TestClient(app)


@pytest.fixture(scope="module")
def raw_provider():
    return InvestmentDataProvider(load_investment_data_config())


@pytest.mark.unit
class TestApiCore:
    def test_health(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["provider"] == "investment_data"

    def test_price_reconciles_raw(self, client, raw_provider):
        resp = client.get(
            "/api/price",
            params={
                "security": TEST_SECURITY,
                "start_date": "2024-01-02",
                "end_date": "2024-01-03",
                "fq": "none",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["security"] == TEST_SECURITY
        assert len(body["rows"]) == 2
        # 与原表对账（同 provider 直读）
        raw = raw_provider.get_price(TEST_SECURITY, "2024-01-02", "2024-01-03", fq="none")
        for r in body["rows"]:
            d = r["date"]
            for col in ("open", "high", "low", "close"):
                assert r[col] == pytest.approx(float(raw.loc[d, col]), rel=1e-9)

    def test_backtest_returns_reproducible_fingerprint(self, client):
        payload = {
            "security": TEST_SECURITY,
            "start_date": START,
            "end_date": END,
            "initial_cash": 500000,
            "amount": 100,
        }
        r1 = client.post("/api/backtest", json=payload)
        r2 = client.post("/api/backtest", json=payload)
        assert r1.status_code == 200 and r2.status_code == 200
        b1, b2 = r1.json(), r2.json()
        assert b1["summary"]["records_count"] > 10
        assert b1["summary"]["final_total_value"] is not None
        assert b1["summary"]["final_total_value"] > 0
        # 同请求两次运行 -> 结果指纹一致（可复现）
        assert b1["snapshot"]["result_fingerprint"] == b2["snapshot"]["result_fingerprint"]

    def test_snapshot_save_load_roundtrip(self, client):
        payload = {
            "security": TEST_SECURITY,
            "start_date": START,
            "end_date": END,
            "initial_cash": 500000,
            "amount": 100,
        }
        bt = client.post("/api/backtest", json=payload).json()
        snap = bt["snapshot"]
        save_resp = client.post(
            "/api/snapshot/save", json={"name": "api_test", "snapshot": snap}
        )
        assert save_resp.status_code == 200
        path = save_resp.json()["path"]
        load_resp = client.get("/api/snapshot/load", params={"path": path})
        assert load_resp.status_code == 200
        loaded = load_resp.json()
        assert loaded["result_fingerprint"] == snap["result_fingerprint"]
        assert loaded["config"] == snap["config"]
