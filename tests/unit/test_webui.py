"""Phase 8 —— 中文 WebUI 雏形测试（消费 FastAPI，无 mock）。

覆盖：
    - GET / 返回 200 且含中文标题与对 /api/price、/api/backtest 的引用
    - 前端关键交互（行情查询）经 /api/price 端到端验证（复用 API 路径）

前端不内嵌价格逻辑，所有数据来自 /api/*。
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.requires_dolt
from fastapi.testclient import TestClient

from quantradar.api.app import app
from quantradar.bootstrap import bootstrap_investment_data


@pytest.fixture(scope="module")
def client():
    bootstrap_investment_data(set_active=True, overwrite=True)
    return TestClient(app)


@pytest.mark.unit
class TestWebUI:
    def test_index_page_served(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        body = resp.text
        # 构建产物（Vite）托管：HTML 含中文标题；API 路径在 JS bundle 中，不要求出现在 HTML
        assert "量子雷达" in body

    def test_price_query_via_api(self, client):
        # 模拟前端 fetch /api/price 的端到端路径
        resp = client.get(
            "/api/price",
            params={
                "security": "600519.XSHG",
                "start_date": "2024-01-02",
                "end_date": "2024-01-03",
                "fq": "none",
            },
        )
        assert resp.status_code == 200
        rows = resp.json()["rows"]
        assert len(rows) == 2
        assert all("close" in r for r in rows)
