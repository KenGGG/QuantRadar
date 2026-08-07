"""PostgreSQL + Worker 集成测试（Closing Phase 2：PERSIST_WORKER_PASS）。

- 未设置 QUANT_RADAR_PG_URL 时整文件 skip（保证套件在缺 PG 环境仍绿）。
- 配置时：在专用 quantradar 库建表，验证 5 张表的 CRUD 与「异步提交 -> Worker 执行 ->
  落库 Snapshot/Metrics/BacktestRun」全链路（复用 run_backtest -> BulletTrade，禁止重实现）。
- 不硬编码凭证；表为本项目专用，测试前后 drop_all 保持隔离。
"""

from __future__ import annotations

import os

import pytest

pg_url = os.environ.get("QUANT_RADAR_PG_URL")

pytestmark = pytest.mark.skipif(
    not pg_url, reason="QUANT_RADAR_PG_URL 未设置：跳过 PostgreSQL 集成测试"
)


@pytest.fixture(scope="module")
def pg():
    from quantradar.storage import drop_all, init_db

    init_db()  # 幂等建表
    yield None
    drop_all()  # 仅作用于专用 quantradar 库，不触碰 investment_data


def test_crud_strategy_and_run(pg):
    from quantradar.storage import (
        create_run,
        get_run,
        save_strategy,
        update_run,
    )

    s = save_strategy("demo", "print('hi')", "hash123")
    assert s.id and s.strategy_hash == "hash123"

    rid = "run_test_001"
    create_run(rid, {"security": "600519.XSHG"}, strategy_id=s.id)
    rec = get_run(rid)
    assert rec["run_id"] == rid
    assert rec["status"] == "PENDING"
    assert rec["strategy_id"] == s.id

    update_run(rid, status="SUCCESS", result_hash="abc")
    rec2 = get_run(rid)
    assert rec2["status"] == "SUCCESS"
    assert rec2["result_hash"] == "abc"


def test_crud_snapshot_and_metrics(pg):
    from quantradar.storage import (
        save_metrics,
        save_snapshot_record,
        update_run,
    )

    rid = "run_snap_001"
    from quantradar.storage import create_run

    create_run(rid, {"security": "600519.XSHG"})
    snap = {"snapshot_id": "snap_xyz", "metrics": {"final_total_value": 1.0}}
    save_snapshot_record(snapshot_id="snap_xyz", run_id=rid, payload=snap, result_hash="reshash")
    save_metrics(run_id=rid, metrics={"final_total_value": 1.0})
    # Worker 会同时把 manifest/指标写回 BacktestRun（贴近真实落库路径）
    update_run(rid, snapshot=snap, metrics={"final_total_value": 1.0})

    from quantradar.storage import get_run, list_runs

    rec = get_run(rid)
    assert rec["snapshot"]["snapshot_id"] == "snap_xyz"
    assert rec["metrics"]["final_total_value"] == 1.0
    assert any(r["run_id"] == rid for r in list_runs(10))


def test_worker_async_backtest_persists(pg):
    """异步提交真实回测，Worker 执行并落入 PostgreSQL。"""
    from quantradar.worker import get_worker

    w = get_worker()
    run_id = w.submit(
        payload={
            "security": "600519.XSHG",
            "start_date": "2023-01-03",
            "end_date": "2023-03-31",
            "initial_cash": 500000.0,
        }
    )["run_id"]
    assert run_id.startswith("run_")

    # 等待后台线程完成（超时 240s）
    w.wait(run_id, timeout=240)

    from quantradar.storage import get_run

    rec = get_run(run_id)
    assert rec is not None, "运行记录应已落库"
    assert rec["status"] == "SUCCESS", f"回测应成功，实际：{rec['status']} / {rec.get('error')}"
    assert rec["result_hash"], "result_hash 应非空"
    assert rec["snapshot"], "Snapshot manifest 应已落库"
    assert rec["snapshot"]["metrics"].get("final_total_value") is not None
    assert rec["metrics"].get("total_return") is not None


def test_worker_user_strategy_persists(pg):
    """用户策略源码异步回测同样落库（验证 code 路径）。"""
    from quantradar.worker import get_worker

    code = (
        "def initialize(context):\n"
        "    context.security = '600519.XSHG'\n"
        "def handle_data(context, data):\n"
        "    if not context.portfolio.positions:\n"
        "        order_target(context.security, 100)\n"
    )
    w = get_worker()
    run_id = w.submit(
        {
            "code": code,
            "start_date": "2023-01-03",
            "end_date": "2023-03-31",
            "initial_cash": 500000.0,
        }
    )["run_id"]
    w.wait(run_id, timeout=240)

    from quantradar.storage import get_run

    rec = get_run(run_id)
    assert rec["status"] == "SUCCESS", rec.get("error")
    assert rec["snapshot"]["strategy_hash"], "用户策略应有 strategy_hash"
