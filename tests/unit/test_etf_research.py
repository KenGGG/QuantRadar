from __future__ import annotations

import numpy as np
import pandas as pd

from quantradar.etf_research import build_weights, preflight


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
