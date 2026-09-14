"""Deterministic Alpha factor evaluation on a date×security panel."""
from __future__ import annotations

import numpy as np
import pandas as pd
from qlib.contrib.eva.alpha import calc_ic

EVALUATION_VERSION = "factorlab-eval-v3"


def split_dates(index: pd.Index, ratios: tuple[float, float, float] = (.6, .2, .2)) -> dict[str, list[pd.Timestamp]]:
    """Deterministically split trading dates; defaults to research/validation/holdout 60/20/20."""
    if len(ratios) != 3 or any(not isinstance(x, (int, float)) or x <= 0 for x in ratios) or not np.isclose(sum(ratios), 1.0):
        raise ValueError("split ratios must be three positive values summing to 1")
    dates = list(pd.DatetimeIndex(index).sort_values().unique())
    n = len(dates)
    research_end, validation_end = int(n * ratios[0]), int(n * (ratios[0] + ratios[1]))
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
    top_members_by_day: list[set[str]] = []
    for day in factor.index:
        joined = pd.DataFrame({"factor": factor.loc[day], "label": label.loc[day]}).dropna()
        if len(joined) < min_cross_section or joined.factor.nunique() < 2 or joined.label.nunique() < 2:
            daily.append({"date": str(pd.Timestamp(day).date()), "ic": None, "rank_ic": None, "count": len(joined), "quantiles": None})
            top_members_by_day.append(set())
            continue
        indexed = joined.copy(); indexed.index = pd.MultiIndex.from_product([[pd.Timestamp(day)], indexed.index], names=["datetime", "instrument"])
        ic, ric = calc_ic(indexed.factor, indexed.label, dropna=False)
        ranks = joined.factor.rank(method="average")
        bins = pd.qcut(ranks, 5, duplicates="drop")
        means = joined.label.groupby(bins, observed=True).mean()
        quantiles = means.tolist() if len(means) == 5 else None
        daily.append({"date": str(pd.Timestamp(day).date()), "ic": float(ic.iloc[0]), "rank_ic": float(ric.iloc[0]), "count": len(joined), "quantiles": quantiles})
        # A deterministic research turnover proxy: entries into the highest
        # average-rank quintile between consecutive evaluable cross-sections.
        top_members_by_day.append(set(joined.index[bins == bins.max()].astype(str)) if quantiles is not None else set())
    frame = pd.DataFrame(daily)
    valid = frame.dropna(subset=["ic"])
    monthly_rank_ic: list[dict[str, float | str]] = []
    if len(valid):
        grouped = valid.assign(month=pd.to_datetime(valid["date"]).dt.to_period("M"))
        monthly_rank_ic = [{"month": str(month), "rank_ic": float(values.rank_ic.mean())}
                           for month, values in grouped.groupby("month", sort=True)]
    rolling = frame.ic.rolling(60, min_periods=60).mean().where(frame.ic.rolling(60, min_periods=60).count() == 60)
    turnovers = []
    previous: set[str] | None = None
    for members in top_members_by_day:
        if not members:
            previous = None
            continue
        if previous:
            turnovers.append(len(members - previous) / len(members))
        previous = members
    return {"evaluation_version": EVALUATION_VERSION, "computed_dates": len(frame), "valid_dates": len(valid),
            "ic_mean": float(valid.ic.mean()) if len(valid) else None, "rank_ic_mean": float(valid.rank_ic.mean()) if len(valid) else None,
            "ic_std": float(valid.ic.std(ddof=1)) if len(valid) > 1 else None,
            "rank_ic_std": float(valid.rank_ic.std(ddof=1)) if len(valid) > 1 else None,
            "rank_ic_positive_ratio": float((valid.rank_ic > 0).mean()) if len(valid) else None,
            "monthly_rank_ic": monthly_rank_ic,
            "rank_ic_positive_month_ratio": float(np.mean([row["rank_ic"] > 0 for row in monthly_rank_ic])) if monthly_rank_ic else None,
            "mean_cross_section": float(valid["count"].mean()) if len(valid) else None,
            "top_quantile_turnover": float(np.mean(turnovers)) if turnovers else None,
            "rolling_60d_ic": [None if pd.isna(x) else float(x) for x in rolling], "daily": daily}
