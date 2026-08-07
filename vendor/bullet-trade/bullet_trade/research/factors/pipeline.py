from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from bullet_trade.core.globals import log


FactorFunc = Callable[[pd.DataFrame], pd.Series]


@dataclass
class FilterConfig:
    skip_paused: bool = True
    skip_st: bool = True
    skip_limit: bool = True
    min_list_days: int = 0
    min_maturity_days: int = 100
    price_top_pct: Optional[float] = None


@dataclass
class FactorPipelineConfig:
    factor_funcs: Dict[str, FactorFunc]
    filter_config: FilterConfig = field(default_factory=FilterConfig)
    winsor_limits: Tuple[float, float] = (0.025, 0.975)
    standardize: str = "zscore"  # or "rank"
    neutralize_industry: bool = False
    neutralize_mcap: bool = False
    factor_weights: Optional[Dict[str, float]] = None


@dataclass
class FactorPipelineResult:
    data: pd.DataFrame
    meta: Dict[str, object]
    filter_counts: Dict[str, int]


def _ensure_date(col: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(col):
        return col.dt.date
    try:
        return pd.to_datetime(col).dt.date
    except Exception:
        return col


def _filter_data(df: pd.DataFrame, config: FilterConfig) -> Tuple[pd.DataFrame, Dict[str, int]]:
    before = len(df)
    counts: Dict[str, int] = {}
    filtered = df.copy()

    def _days_between(later: pd.Series, earlier: pd.Series) -> pd.Series:
        try:
            later_dt = pd.to_datetime(later)
            earlier_dt = pd.to_datetime(earlier)
            return (later_dt - earlier_dt).dt.days
        except Exception:
            return pd.Series([np.nan] * len(later), index=later.index)

    if config.skip_paused and "paused" in filtered.columns:
        mask = filtered["paused"].astype(bool)
        counts["paused"] = int(mask.sum())
        filtered = filtered.loc[~mask]

    if config.skip_st:
        st_cols = [c for c in filtered.columns if c.lower() in ("is_st", "st", "st_flag")]
        if st_cols:
            mask = filtered[st_cols[0]].astype(bool)
            counts["st"] = int(mask.sum())
            filtered = filtered.loc[~mask]

    if config.skip_limit:
        close_col = "close" if "close" in filtered.columns else None
        if close_col and "high_limit" in filtered.columns:
            mask = filtered[close_col] >= filtered["high_limit"]
            counts["limit_up"] = int(mask.sum())
            filtered = filtered.loc[~mask]
        if close_col and "low_limit" in filtered.columns:
            mask = filtered[close_col] <= filtered["low_limit"]
            counts["limit_down"] = int(mask.sum())
            filtered = filtered.loc[~mask]

    if config.min_list_days and "list_date" in filtered.columns and "date" in filtered.columns:
        list_days = _days_between(filtered["date"], filtered["list_date"])
        mask = list_days < config.min_list_days
        counts["list_days"] = int(mask.sum())
        filtered = filtered.loc[~mask]

    if config.min_maturity_days and "maturity_date" in filtered.columns and "date" in filtered.columns:
        maturity_days = _days_between(filtered["maturity_date"], filtered["date"])
        mask = maturity_days < config.min_maturity_days
        counts["maturity"] = int(mask.sum())
        filtered = filtered.loc[~mask]

    if config.price_top_pct and "close" in filtered.columns:
        pct = min(max(config.price_top_pct, 0.0), 1.0)
        cutoff = filtered["close"].quantile(1 - pct)
        mask = filtered["close"] >= cutoff
        counts["price_top_pct"] = int(mask.sum())
        filtered = filtered.loc[~mask]

    counts["kept"] = len(filtered)
    counts["dropped"] = before - len(filtered)
    return filtered, counts


def _winsorize(series: pd.Series, limits: Tuple[float, float]) -> pd.Series:
    lower, upper = limits
    lower_q, upper_q = series.quantile([lower, upper])
    return series.clip(lower_q, upper_q)


def _standardize(series: pd.Series, method: str) -> pd.Series:
    if method == "rank":
        return series.rank(pct=True)
    std = series.std()
    if std == 0 or pd.isna(std):
        return series * 0
    return (series - series.mean()) / std


def _neutralize_industry(series: pd.Series, industries: pd.Series) -> pd.Series:
    if industries is None:
        return series
    grouped = series.groupby(industries)
    return series - grouped.transform("mean")


def _neutralize_mcap(series: pd.Series, mcap: pd.Series) -> pd.Series:
    if mcap is None or series.isna().all():
        return series
    valid_mask = (~series.isna()) & (~mcap.isna()) & (mcap > 0)
    if valid_mask.sum() < 2:
        return series
    x = np.log(mcap[valid_mask])
    y = series[valid_mask]
    x = np.vstack([np.ones(len(x)), x]).T
    beta, _, _, _ = np.linalg.lstsq(x, y, rcond=None)
    fitted = x @ beta
    adjusted = series.copy()
    adjusted.loc[valid_mask] = y - fitted + y.mean()
    return adjusted


def run_factor_pipeline(df: pd.DataFrame, config: FactorPipelineConfig) -> FactorPipelineResult:
    working = df.copy()
    if "date" in working.columns:
        working["date"] = _ensure_date(working["date"])

    for name, func in config.factor_funcs.items():
        try:
            working[name] = func(working)
        except Exception as exc:
            log.warning("因子计算失败: %s, 错误: %s", name, exc)
            working[name] = np.nan

    filtered, filter_counts = _filter_data(working, config.filter_config)
    factor_names = list(config.factor_funcs.keys())
    if not factor_names:
        raise ValueError("factor_funcs 不能为空")

    for name in factor_names:
        series = filtered[name]
        series = _winsorize(series, config.winsor_limits)
        series = _standardize(series, config.standardize)
        if config.neutralize_industry and "industry" in filtered.columns:
            series = _neutralize_industry(series, filtered["industry"])
        if config.neutralize_mcap:
            mcap_col = None
            for col in ("market_cap", "circulating_market_cap", "total_mv", "circ_mv"):
                if col in filtered.columns:
                    mcap_col = col
                    break
            if mcap_col:
                series = _neutralize_mcap(series, filtered[mcap_col])
        filtered[name] = series

    weights: Dict[str, float] = {}
    if config.factor_weights:
        weights.update(config.factor_weights)
    else:
        weights = {n: 1.0 / len(factor_names) for n in factor_names}

    missing = [n for n in factor_names if n not in weights]
    if missing:
        default_w = 1.0 / len(factor_names)
        for n in missing:
            weights[n] = default_w

    filtered["composite_score"] = 0.0
    for name, w in weights.items():
        filtered["composite_score"] = filtered["composite_score"] + filtered[name] * w

    meta = {
        "config": asdict(config),
        "weights": weights,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
    return FactorPipelineResult(data=filtered, meta=meta, filter_counts=filter_counts)


__all__ = [
    "FactorPipelineConfig",
    "FilterConfig",
    "FactorPipelineResult",
    "run_factor_pipeline",
]
