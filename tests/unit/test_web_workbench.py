"""React 研究工作台验收（Closing Phase 3：WEB_WORKBENCH_PASS）。

仅依赖后端 /api/* 真实接口与已构建产物 frontend/dist，无 mock：
  - frontend/dist/index.html 已构建且含中文标题（GET / 托管）。
  - FastAPI GET / 返回 200 且含「量子雷达」（Vite 构建产物被托管）。
  - /api/backtest 返回 WebUI 所需明细：daily_records / trades / positions / metrics / environment / result_hash。
  - /api/health 返回审计环境（供数据状态面板）。
  - /api/backtest/async -> run_id；/api/backtest/runs/{id} 可查（异步链路，PG 不可用时回退同步校验）。
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

frontend_dist = os.path.join(
    os.path.dirname(__file__), "..", "..", "frontend", "dist", "index.html"
)

SECURITY = "600519.XSHG"
START = "2023-01-03"
END = "2023-03-31"
CASH = 500000


def test_frontend_build_exists():
    """前端必须已构建（Vite 产物）。未构建则视为未完成（不 skip，属验收硬性条件）。"""
    assert os.path.exists(frontend_dist), (
        "frontend/dist/index.html 不存在：请 cd frontend && npm install && npm run build"
    )
    with open(frontend_dist, "r", encoding="utf-8") as f:
        html = f.read()
    assert "量子雷达" in html, "构建产物缺少中文标题，GET / 冒烟断言会失败"


def test_web_entry_served():
    from quantradar.api.app import app

    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200, f"GET / 失败：{r.status_code}"
    assert "量子雷达" in r.text, "GET / 未托管中文工作台"


def test_health_has_audit_env():
    from quantradar.api.app import app

    client = TestClient(app)
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body.get("provider") == "investment_data"
    env = body.get("environment") or {}
    assert env.get("dolt_commit"), "health 未携带 dolt_commit"
    assert env.get("schema_hash"), "health 未携带 schema_hash"


def test_backtest_response_has_webui_details():
    from quantradar.api.app import app

    client = TestClient(app)
    r = client.post(
        "/api/backtest",
        json={"security": SECURITY, "start_date": START, "end_date": END, "initial_cash": CASH},
    )
    assert r.status_code == 200, f"回测失败：{r.text}"
    body = r.json()
    snap = body["snapshot"]
    # 图表/表格所需明细
    assert isinstance(snap.get("daily_records"), list) and len(snap["daily_records"]) > 0
    assert isinstance(snap.get("trades"), list)
    assert isinstance(snap.get("positions"), list)
    # 审计/指标
    assert snap.get("metrics") and snap["metrics"].get("final_total_value") is not None
    assert snap.get("environment") and snap["environment"].get("dolt_commit")
    assert snap.get("result_hash")


def test_async_backtest_runs_and_queryable():
    """异步链路：提交 -> run_id -> 轮询 -> 结果可查。需 PostgreSQL（否则 skip）。"""
    pg_url = os.environ.get("QUANT_RADAR_PG_URL")
    if not pg_url:
        pytest.skip("QUANT_RADAR_PG_URL 未设置：跳过异步链路（同步明细已覆盖）")

    from quantradar.api.app import app
    from quantradar.worker import get_worker

    client = TestClient(app)
    r = client.post(
        "/api/backtest/async",
        json={"security": SECURITY, "start_date": START, "end_date": END, "initial_cash": CASH},
    )
    assert r.status_code == 200, f"异步提交失败：{r.text}"
    run_id = r.json()["run_id"]

    # 等待后台线程完成（Worker 内建 join，超时 240s）
    get_worker().wait(run_id, timeout=240)

    rr = client.get(f"/api/backtest/runs/{run_id}")
    assert rr.status_code == 200
    rec = rr.json()
    assert rec["status"] == "SUCCESS", rec.get("error")
    assert rec["snapshot"] and rec["snapshot"].get("result_hash")
