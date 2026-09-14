from __future__ import annotations

import numpy as np
import pandas as pd

from quantradar.factorlab.evaluation import evaluate, forward_open_label


def test_labels_never_use_same_day_open():
    values = pd.DataFrame({"a": range(10), "b": range(10, 20)}, index=pd.date_range("2020-01-01", periods=10))
    labels = forward_open_label(values, 1)
    assert labels.iloc[0, 0] == values.iloc[2, 0] / values.iloc[1, 0] - 1
    assert pd.isna(labels.iloc[-2, 0])


def test_evaluation_requires_full_cross_section_and_full_rolling_window():
    dates = pd.date_range("2020-01-01", periods=61)
    columns = [f"s{i:02}" for i in range(20)]
    data = np.tile(np.arange(20, dtype=float), (61, 1))
    result = evaluate(pd.DataFrame(data, index=dates, columns=columns), pd.DataFrame(data, index=dates, columns=columns))
    assert result["valid_dates"] == 61
    assert result["rolling_60d_ic"][58] is None
    assert result["rolling_60d_ic"][59] == 1.0
