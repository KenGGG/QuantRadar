from __future__ import annotations

import numpy as np
import pandas as pd

from quantradar.etf_research import build_execution_artifacts, build_weights, preflight
from quantradar.portfolio.target_weight_bridge import build_effective_weight_strategy


def _panel(days: int = 140) -> pd.DataFrame:
    index = pd.date_range("2021-01-01", periods=days, freq="B")
    return pd.DataFrame({"510050.SH": np.arange(days, dtype=float) + 10,
                         "510300.SH": np.arange(days, dtype=float) + 20,
                         "510500.SH": np.arange(days, dtype=float) + 30}, index=index)


def test_preflight_only_blocks_template_dependency():
    panel = _panel()
    panel.loc[panel.index[5], "510050.SH"] = np.nan
    equal = preflight(panel, "equal_weight", "2021-03-01", "2021-03-31")
    trend = preflight(panel, "trend", "2021-03-01", "2021-03-31")
    assert not equal["blocked"]
    assert trend["blocked"]


def test_weight_artifact_has_signal_and_effective_dates():
    panel = _panel()
    result = build_weights(panel, "momentum", "2021-04-01", "2021-06-30")
    assert {"signal_date", "effective_date", "security", "target_weight", "reason"} <= set(result.columns)
    assert (result.groupby("effective_date").target_weight.sum() <= 1).all()
    assert (pd.to_datetime(result.effective_date) > pd.to_datetime(result.signal_date)).all()


def test_effective_open_is_a_dependency_but_not_the_signal_close():
    panel = _panel()
    opens = panel.copy()
    opens.loc[pd.Timestamp("2021-03-01"), "510050.SH"] = np.nan
    panel.attrs["open"] = opens
    check = preflight(panel, "equal_weight", "2021-03-01", "2021-03-31")
    assert check["blocked"]
    assert any(x["field"] == "open" and x["effective_date"] == "2021-03-01" for x in check["missing"])

    result = build_weights(_panel(), "momentum", "2021-04-01", "2021-06-30")
    assert (pd.to_datetime(result.effective_date) > pd.to_datetime(result.signal_date)).all()


def test_etf_strategy_uses_native_fund_cost_and_bps_slippage(tmp_path):
    code = build_effective_weight_strategy(tmp_path / "weights.csv", etf_raw=True,
        order_cost={"open_tax": 0, "close_tax": 0, "open_commission": .0003, "close_commission": .0003, "min_commission": 5},
        slippage_ratio=.0004)
    assert "set_order_cost(OrderCost" in code and "type='fund'" in code
    assert "PriceRelatedSlippage(0.0004)" in code and 'current_bar_fq", "none' in code


def test_execution_artifacts_keep_target_actual_and_native_orders(tmp_path):
    weights = tmp_path / "weights.csv"
    pd.DataFrame([{"signal_date":"2021-01-01","effective_date":"2021-01-04","security":"510050.SH","target_weight":1.0,"signal_value":"x","reason":"x"}]).to_csv(weights,index=False)
    run = tmp_path / "run"; run.mkdir()
    pd.DataFrame([{"date":"2021-01-04 15:00:00","code":"510050.SH","value":900,"total_value":1000}]).to_csv(run / "daily_positions.csv",index=False)
    pd.DataFrame([{"标的":"510050.SH","方向":"买入"}]).to_csv(run / "trades.csv",index=False,encoding="utf-8-sig")
    artifacts = build_execution_artifacts(weights, run, tmp_path / "artifacts")
    compare = pd.read_csv(artifacts["target_vs_actual"])
    assert np.isclose(compare.loc[0,"actual_weight"], .9) and np.isclose(compare.loc[0,"weight_difference"], -.1)
    assert (tmp_path / "artifacts" / "orders.csv").is_file()
