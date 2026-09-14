from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quantradar.factorlab.evaluation import dates_within_label_window, evaluate, forward_open_label, split_dates


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
    assert result["rank_ic_positive_ratio"] == 1.0
    assert result["rank_ic_positive_month_ratio"] == 1.0
    assert len(result["monthly_rank_ic"]) == 3
    assert result["mean_cross_section"] == 20.0
    assert result["top_quantile_turnover"] == 0.0


def test_split_excludes_labels_that_cross_a_boundary():
    dates = pd.date_range("2024-01-01", periods=20, freq="B")
    splits = split_dates(dates)
    assert [len(splits[x]) for x in ("research", "validation", "holdout")] == [12, 4, 4]
    assert dates[11] not in dates_within_label_window(splits["research"], dates, 1)
    assert dates[16] in dates_within_label_window(splits["holdout"], dates, 1)


def test_split_requires_a_complete_positive_partition():
    with pytest.raises(ValueError):
        split_dates(pd.date_range("2024-01-01", periods=10), (.5, .5, .5))
