from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from bullet_trade.core.globals import log


@dataclass
class CostConfig:
    commission_buy: float = 0.00044
    commission_sell: float = 0.00044
    tax_buy: float = 0.0
    tax_sell: float = 0.001
    slippage: float = 0.0
    fixed_fee: float = 0.0  # 每笔固定费用
    capital_base: float = 1.0  # 资金规模，用于将固定费用转为收益率


@dataclass
class BacktestConfig:
    n_buckets: int = 10
    long_buckets: Optional[List[int]] = None
    short_buckets: Optional[List[int]] = None
    rebalance: str = "1d"  # '1d', '1w', '1m'
    frequency: str = "daily"
    factor_col: str = "composite_score"
    return_col: str = "forward_return"

    def __post_init__(self):
        if self.long_buckets is None:
            self.long_buckets = [self.n_buckets]
        if self.short_buckets is None:
            self.short_buckets = []


@dataclass
class EvaluationResult:
    bucket_returns: pd.DataFrame
    ic: pd.Series
    rank_ic: pd.Series
    portfolio_returns: pd.DataFrame
    metrics: Dict[str, float]
    meta: Dict[str, object]


def _assign_buckets(df: pd.DataFrame, factor_col: str, n_buckets: int) -> pd.Series:
    def _bucket_for_group(group: pd.Series) -> pd.Series:
        valid = group.dropna()
        if valid.empty:
            return pd.Series(np.nan, index=group.index)
        try:
            buckets = pd.qcut(valid.rank(method="first"), n_buckets, labels=False) + 1
        except ValueError:
            buckets = pd.Series(np.nan, index=valid.index)
        out = pd.Series(np.nan, index=group.index)
        out.loc[valid.index] = buckets
        return out

    return df.groupby("date")[factor_col].transform(_bucket_for_group)


def _compute_ic(df: pd.DataFrame, factor_col: str, return_col: str, method: str = "pearson") -> pd.Series:
    correlations = {}
    for dt, group in df.groupby("date"):
        if group[factor_col].count() < 2 or group[return_col].count() < 2:
            correlations[dt] = np.nan
            continue
        try:
            if method == "spearman":
                correlations[dt] = group[[factor_col, return_col]].corr(method="spearman").iloc[0, 1]
            else:
                correlations[dt] = group[[factor_col, return_col]].corr().iloc[0, 1]
        except Exception:
            correlations[dt] = np.nan
    return pd.Series(correlations).sort_index()


def _calc_turnover(prev_codes: set, current_codes: set) -> Tuple[float, int]:
    if not prev_codes and not current_codes:
        return 0.0, 0
    if not prev_codes:
        return 1.0, len(current_codes)
    overlap = len(prev_codes.intersection(current_codes))
    total = len(prev_codes.union(current_codes))
    if total == 0:
        return 0.0, 0
    turnover = 1.0 - overlap / total
    trades = len(prev_codes.symmetric_difference(current_codes))
    return turnover, trades


def evaluate_factor_performance(
    df: pd.DataFrame, backtest_cfg: BacktestConfig, cost_cfg: Optional[CostConfig] = None
) -> EvaluationResult:
    cost_cfg = cost_cfg or CostConfig()
    working = df.copy()
    if "date" in working.columns:
        working["date"] = pd.to_datetime(working["date"]).dt.date

    factor_col = backtest_cfg.factor_col
    return_col = backtest_cfg.return_col
    if factor_col not in working.columns:
        raise ValueError(f"缺少因子列: {factor_col}")
    if return_col not in working.columns:
        raise ValueError(f"缺少收益列: {return_col}")

    working["bucket"] = _assign_buckets(working, factor_col, backtest_cfg.n_buckets)

    bucket_returns = (
        working.dropna(subset=["bucket", return_col])
        .groupby(["date", "bucket"])[return_col]
        .mean()
        .reset_index()
        .sort_values(["date", "bucket"])
    )

    ic = _compute_ic(working, factor_col, return_col, method="pearson")
    rank_ic = _compute_ic(working, factor_col, return_col, method="spearman")

    # 组合收益计算
    portfolio_rows: List[Dict[str, object]] = []
    prev_positions: set = set()
    cost_rate = (
        cost_cfg.commission_buy
        + cost_cfg.commission_sell
        + cost_cfg.tax_buy
        + cost_cfg.tax_sell
        + cost_cfg.slippage
    )

    for dt, group in working.groupby("date"):
        long_mask = group["bucket"].isin(backtest_cfg.long_buckets)
        short_mask = group["bucket"].isin(backtest_cfg.short_buckets)

        has_long = bool(long_mask.any())
        has_short = bool(short_mask.any())

        long_ret = group.loc[long_mask, return_col].mean() if has_long else np.nan
        short_ret = group.loc[short_mask, return_col].mean() if has_short else np.nan

        current_positions = set(group.loc[long_mask | short_mask, "code"].dropna().tolist())

        # 无持仓则不计收益/成本，避免净值被空仓成本侵蚀
        if not has_long and not has_short:
            turnover, trades = _calc_turnover(prev_positions, current_positions)
            portfolio_rows.append(
                {
                    "date": dt,
                    "gross_return": 0.0,
                    "net_return": 0.0,
                    "turnover": turnover,
                    "trades": trades,
                    "cost": 0.0,
                    "long_size": 0,
                    "short_size": 0,
                }
            )
            prev_positions = current_positions
            continue

        gross_return = 0.0
        if has_long and not np.isnan(long_ret):
            gross_return += long_ret
        if has_short and not np.isnan(short_ret):
            gross_return -= short_ret

        turnover, trades = _calc_turnover(prev_positions, current_positions)
        cost = turnover * cost_rate
        if cost_cfg.capital_base and cost_cfg.capital_base > 0:
            cost += (cost_cfg.fixed_fee / cost_cfg.capital_base) * trades
        else:
            cost += cost_cfg.fixed_fee * trades
        net_return = gross_return - cost

        portfolio_rows.append(
            {
                "date": dt,
                "gross_return": gross_return,
                "net_return": net_return,
                "turnover": turnover,
                "trades": trades,
                "cost": cost,
                "long_size": int(long_mask.sum()),
                "short_size": int(short_mask.sum()),
            }
        )
        prev_positions = current_positions

    portfolio_df = pd.DataFrame(portfolio_rows).sort_values("date")

    metrics = {
        "ic_mean": float(ic.mean()),
        "rank_ic_mean": float(rank_ic.mean()),
        "avg_turnover": float(portfolio_df["turnover"].mean()) if not portfolio_df.empty else 0.0,
        "avg_cost": float(portfolio_df["cost"].mean()) if not portfolio_df.empty else 0.0,
    }

    meta = {
        "backtest_config": asdict(backtest_cfg),
        "cost_config": asdict(cost_cfg),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }

    return EvaluationResult(
        bucket_returns=bucket_returns,
        ic=ic,
        rank_ic=rank_ic,
        portfolio_returns=portfolio_df,
        metrics=metrics,
        meta=meta,
    )


__all__ = [
    "CostConfig",
    "BacktestConfig",
    "EvaluationResult",
    "evaluate_factor_performance",
]
