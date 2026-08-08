"""Phase 9 Experiment（目标口径）—— 基于 Snapshot 的存证与对比（无 mock，本地 JSON）。"""

from __future__ import annotations

import pytest

from bullet_trade import order_target
from bullet_trade.core.engine import BacktestEngine

from quantradar.bootstrap import bootstrap_investment_data
from quantradar.experiment import (
    Experiment,
    compare_experiments,
    list_experiments,
    load_experiment,
    save_experiment,
)
from quantradar.snapshot import build_snapshot

pytestmark = [pytest.mark.unit, pytest.mark.requires_dolt]


def _make_snapshot_fingerprint(seed: str) -> str:
    return "fp_" + seed


def test_save_and_load_roundtrip(tmp_path):
    exp = Experiment(
        name="exp_a",
        kind="backtest",
        config={"initial_cash": 500000, "start_date": "2023-01-03", "end_date": "2023-03-31"},
        result_fingerprint=_make_snapshot_fingerprint("a"),
        metrics={"final_total_value": 505000.0, "return": 0.01},
    )
    path = save_experiment(exp, directory=str(tmp_path))
    assert path.endswith("exp_a.json")
    loaded = load_experiment("exp_a", directory=str(tmp_path))
    assert loaded.name == "exp_a"
    assert loaded.result_fingerprint == _make_snapshot_fingerprint("a")
    assert loaded.metrics["final_total_value"] == 505000.0


def test_list_and_compare(tmp_path):
    a = Experiment(
        name="a",
        kind="backtest",
        config={"initial_cash": 500000},
        result_fingerprint="fp_a",
        metrics={"return": 0.01},
    )
    b = Experiment(
        name="b",
        kind="backtest",
        config={"initial_cash": 1000000},
        result_fingerprint="fp_b",
        metrics={"return": 0.02},
    )
    save_experiment(a, directory=str(tmp_path))
    save_experiment(b, directory=str(tmp_path))
    names = list_experiments(directory=str(tmp_path))
    assert set(names) == {"a", "b"}

    cmp = compare_experiments(["a", "b"], directory=str(tmp_path))
    assert cmp["fingerprint_match"] is False  # 不同指纹
    assert len(cmp["experiments"]) == 2
    # 指标可横向对比
    metrics = {e["name"]: e["metrics"]["return"] for e in cmp["experiments"]}
    assert metrics == {"a": 0.01, "b": 0.02}


def test_experiment_from_backtest_roundtrip():
    """从真实回测构造 Experiment（含 Snapshot 指纹），保存后指纹一致。"""
    import tempfile

    from quantradar.bootstrap import bootstrap_investment_data as boot

    p = boot(set_active=True, overwrite=True)
    state: dict = {}

    def _init(context):  # noqa: ANN001
        state["bought"] = False

    def _handle(context, data):  # noqa: ANN001
        df = p.get_price("600519.XSHG", count=5, fields=["close"])
        if df is None or df.empty:
            return
        if not state["bought"]:
            order_target("600519.XSHG", 100)
            state["bought"] = True

    engine = BacktestEngine(
        initialize=_init,
        handle_data=_handle,
        start_date="2023-01-03",
        end_date="2023-03-31",
        frequency="day",
        initial_cash=500000,
    )
    engine.run()
    snap = build_snapshot(engine)
    exp = Experiment(
        name="real_a",
        kind="backtest",
        config=snap.get("config", {}),
        result_fingerprint=snap.get("result_fingerprint", ""),
        metrics={},
        snapshot=snap,
    )
    d = tempfile.mkdtemp()
    save_experiment(exp, directory=d)
    loaded = load_experiment("real_a", directory=d)
    assert loaded.result_fingerprint == snap["result_fingerprint"]
    assert loaded.snapshot is not None
