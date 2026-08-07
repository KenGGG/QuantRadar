"""Phase 6 —— Snapshot / 可复现性测试（DB-backed）。

覆盖：
    - 同配置两次运行 daily_records 逐日一致（确定性核心断言）
    - build/save/load 快照 round-trip：环境与结果指纹完整还原
    - 结果指纹对配置（initial_cash）变化敏感

所有回测均经 InvestmentDataProvider 读取真实 investment_data，禁止 mock。
"""

from __future__ import annotations

import os

import pytest

from bullet_trade.core.engine import BacktestEngine

from quantradar.bootstrap import bootstrap_investment_data
from quantradar.snapshot import (
    build_snapshot,
    daily_records_fingerprint,
    load_snapshot,
    save_snapshot,
)

TEST_SECURITY = "600519.XSHG"
START = "2023-01-03"
END = "2023-03-31"


@pytest.fixture(scope="module")
def active_provider():
    return bootstrap_investment_data(set_active=True, overwrite=True)


_STATE = {"bought": False}


def _init(context):  # noqa: ANN001
    _STATE["bought"] = False


def _handle(context, data):  # noqa: ANN001
    df = get_price(TEST_SECURITY, count=5, fields=["close"])
    if df is None or df.empty:
        return
    if not _STATE["bought"]:
        order_target(TEST_SECURITY, 100)
        _STATE["bought"] = True


def _run(initial_cash: float = 500000) -> BacktestEngine:
    _STATE["bought"] = False
    engine = BacktestEngine(
        initialize=_init,
        handle_data=_handle,
        start_date=START,
        end_date=END,
        frequency="day",
        initial_cash=initial_cash,
    )
    engine.run()
    return engine


@pytest.mark.unit
class TestReproducibility:
    def test_same_config_runs_are_deterministic(self, active_provider):
        e1 = _run()
        e2 = _run()
        assert daily_records_fingerprint(e1.daily_records) == daily_records_fingerprint(
            e2.daily_records
        )
        # 逐日总资产一致
        v1 = [round(r["total_value"], 4) for r in e1.daily_records]
        v2 = [round(r["total_value"], 4) for r in e2.daily_records]
        assert v1 == v2

    def test_snapshot_roundtrip(self, active_provider, tmp_path):
        engine = _run()
        snap = build_snapshot(engine, extras={"universe": [TEST_SECURITY]})
        assert snap["result_fingerprint"] == daily_records_fingerprint(engine.daily_records)
        assert snap["config"]["initial_cash"] == 500000
        assert snap["records_count"] == len(engine.daily_records)

        path = os.path.join(str(tmp_path), "snap.json")
        save_snapshot(snap, path)
        loaded = load_snapshot(path)
        assert loaded["result_fingerprint"] == snap["result_fingerprint"]
        assert loaded["config"] == snap["config"]
        assert loaded["data_asof"] == snap["data_asof"]
        assert loaded["extras"] == snap["extras"]

    def test_fingerprint_sensitive_to_config(self, active_provider):
        e_low = _run(initial_cash=500000)
        e_high = _run(initial_cash=600000)
        fp_low = daily_records_fingerprint(e_low.daily_records)
        fp_high = daily_records_fingerprint(e_high.daily_records)
        # 不同初始资金 -> 不同资产曲线 -> 不同指纹
        assert fp_low != fp_high
