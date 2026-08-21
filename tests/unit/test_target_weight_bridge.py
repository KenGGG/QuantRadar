from __future__ import annotations

import pandas as pd

from quantradar.portfolio.target_weight_bridge import select_effective_weight_date


def test_execution_date_is_eligible_on_that_day_but_not_before():
    index = pd.DatetimeIndex(["2022-06-27", "2022-07-04"])
    assert select_effective_weight_date(index, "2022-06-26") is None
    assert select_effective_weight_date(index, "2022-06-27 09:30") == pd.Timestamp("2022-06-27")
    assert select_effective_weight_date(index, "2022-07-01") == pd.Timestamp("2022-06-27")
    assert select_effective_weight_date(index, "2022-07-04") == pd.Timestamp("2022-07-04")
