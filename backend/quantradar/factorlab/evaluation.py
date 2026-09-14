"""Deterministic Alpha factor evaluation on a date×security panel."""
from __future__ import annotations

import numpy as np
import pandas as pd
from qlib.contrib.eva.alpha import calc_ic

EVALUATION_VERSION = "factorlab-eval-v1"


def split_dates(index: pd.Index) -> dict[str, list[pd.Timestamp]]:
    """Deterministically split the requested trading dates 60/20/20."""
    dates = list(pd.DatetimeIndex(index).sort_values().unique())
    n = len(dates)
    research_end, validation_end = int(n * .6), int(n * .8)
    return {"research": dates[:research_end], "validation": dates[research_end:validation_end], "holdout": dates[validation_end:]}


def dates_within_label_window(dates: list[pd.Timestamp], all_dates: pd.Index, horizon: int) -> list[pd.Timestamp]:
    """Keep t only when open(t+1) and open(t+h+1) remain in this split."""
    positions = {pd.Timestamp(d): pos for pos, d in enumerate(pd.DatetimeIndex(all_dates))}
    allowed = set(pd.Timestamp(d) for d in dates)
    return [pd.Timestamp(day) for day in dates
            if positions[pd.Timestamp(day)] + horizon + 1 < len(all_dates)
            and pd.Timestamp(all_dates[positions[pd.Timestamp(day)] + 1]) in allowed
            and pd.Timestamp(all_dates[positions[pd.Timestamp(day)] + horizon + 1]) in allowed]


def forward_open_label(open_panel: pd.DataFrame, horizon: int) -> pd.DataFrame:
    if horizon not in (1, 5, 20):
        raise ValueError("horizon must be one of 1, 5, 20")
    return open_panel.shift(-(horizon + 1)) / open_panel.shift(-1) - 1


def evaluate(factor: pd.DataFrame, label: pd.DataFrame, *, min_cross_section: int = 20) -> dict:
    if not factor.index.equals(label.index) or not factor.columns.equals(label.columns):
        raise ValueError("factor and label must share aligned date×security axes")
    daily = []
    for day in factor.index:
        joined = pd.DataFrame({"factor": factor.loc[day], "label": label.loc[day]}).dropna()
        if len(joined) < min_cross_section or joined.factor.nunique() < 2 or joined.label.nunique() < 2:
            daily.append({"date": str(pd.Timestamp(day).date()), "ic": None, "rank_ic": None, "count": len(joined), "quantiles": None})
            continue
        indexed = joined.copy(); indexed.index = pd.MultiIndex.from_product([[pd.Timestamp(day)], indexed.index], names=["datetime", "instrument"])
        ic, ric = calc_ic(indexed.factor, indexed.label, dropna=False)
        ranks = joined.factor.rank(method="average")
        bins = pd.qcut(ranks, 5, duplicates="drop")
        means = joined.label.groupby(bins, observed=True).mean()
        quantiles = means.tolist() if len(means) == 5 else None
        daily.append({"date": str(pd.Timestamp(day).date()), "ic": float(ic.iloc[0]), "rank_ic": float(ric.iloc[0]), "count": len(joined), "quantiles": quantiles})
    frame = pd.DataFrame(daily)
    valid = frame.dropna(subset=["ic"])
    rolling = frame.ic.rolling(60, min_periods=60).mean().where(frame.ic.rolling(60, min_periods=60).count() == 60)
    return {"evaluation_version": EVALUATION_VERSION, "computed_dates": len(frame), "valid_dates": len(valid),
            "ic_mean": float(valid.ic.mean()) if len(valid) else None, "rank_ic_mean": float(valid.rank_ic.mean()) if len(valid) else None,
            "ic_std": float(valid.ic.std(ddof=1)) if len(valid) > 1 else None,
            "rolling_60d_ic": [None if pd.isna(x) else float(x) for x in rolling], "daily": daily}
