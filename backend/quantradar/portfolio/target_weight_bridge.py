from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from quantradar.backtest_run import run_unified_backtest


def select_effective_weight_date(weights_index: Any, day: Any) -> pd.Timestamp | None:
    index = pd.DatetimeIndex(weights_index).normalize()
    current = pd.Timestamp(day).normalize()
    eligible = index[index <= current]
    return None if eligible.empty else eligible[-1]


def build_effective_weight_strategy(weights_csv: str | Path, *, etf_raw: bool = False,
                                    order_cost: Mapping[str, Any] | None = None,
                                    slippage_ratio: float = 0.0) -> str:
    cost = dict(order_cost or {})
    cost_literal = repr({"open_tax": float(cost.get("open_tax", 0)), "close_tax": float(cost.get("close_tax", 0)),
                         "open_commission": float(cost.get("open_commission", .0003)), "close_commission": float(cost.get("close_commission", .0003)),
                         "min_commission": float(cost.get("min_commission", 5))})
    return f'''# QuantRadar: effective-dated Target Weight -> BulletTrade
import pandas as pd

_WEIGHTS = pd.read_csv(r"{Path(weights_csv).resolve()}", parse_dates=['effective_date'])
_LAST_APPLIED = None

def _rebalance(context):
    global _LAST_APPLIED
    day = pd.Timestamp(context.current_dt).normalize()
    eligible = _WEIGHTS[_WEIGHTS.effective_date <= day]
    if eligible.empty:
        return
    effective_date = eligible.effective_date.max()
    if _LAST_APPLIED is not None and effective_date <= _LAST_APPLIED:
        return
    row = _WEIGHTS[_WEIGHTS.effective_date == effective_date]
    total = context.portfolio.total_value
    targets = set()
    for _, item in row.iterrows():
        security, weight = item.security, item.target_weight
        if pd.notna(weight) and float(weight) > 0:
            targets.add(security)
    # Sell first so the following target buys see released cash.
    for security in list(context.portfolio.positions.keys()):
        if security not in targets:
            order_target_value(security, 0.0)
    for _, item in row.iterrows():
        security, weight = item.security, item.target_weight
        if pd.notna(weight) and float(weight) > 0:
            order_target_value(security, float(weight) * total)
    _LAST_APPLIED = effective_date

def initialize(context):
    {'set_option("current_bar_fq", "none")' if etf_raw else 'pass'}
    set_order_cost(OrderCost(**{cost_literal}), type='fund')
    set_slippage(PriceRelatedSlippage({float(slippage_ratio)!r}), type='fund')

run_daily(_rebalance, '09:30')
'''


def build_monthly_signal_weight_strategy(weights_csv: str | Path) -> str:
    """Build the legacy Qlib monthly strategy with strict prior-day signals."""
    return f'''# QuantRadar: signal-dated Target Weight -> BulletTrade monthly rebalance
import pandas as pd

_WEIGHTS = pd.read_csv(r"{Path(weights_csv).resolve()}", index_col=0, parse_dates=True)

def _rebalance(context):
    day = pd.Timestamp(context.current_dt).normalize()
    eligible = _WEIGHTS.index[_WEIGHTS.index < day]
    if eligible.empty:
        return
    row = _WEIGHTS.loc[eligible[-1]]
    total = context.portfolio.total_value
    targets = set()
    for security, weight in row.items():
        if pd.notna(weight) and float(weight) > 0:
            order_target_value(security, float(weight) * total)
            targets.add(security)
    for security in list(context.portfolio.positions.keys()):
        if security not in targets:
            order_target_value(security, 0.0)

def initialize(context):
    pass

run_monthly(_rebalance, 1, '09:30')
'''


def run_unified_target_weight_backtest(
    weights: pd.DataFrame,
    *,
    run_id: str,
    start_date: str,
    end_date: str,
    initial_cash: float = 1_000_000.0,
    fq: str = "pre",
    benchmark: str = "000300.XSHG",
    release_id: str | None = None,
    runs_dir: str | Path | None = None,
    extras: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if weights is None or weights.empty:
        raise ValueError("Target Weight is empty")
    root = Path(runs_dir) if runs_dir is not None else Path.cwd() / "runs"
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    weights_csv = run_dir / "target_weights.csv"
    required = {"signal_date", "effective_date", "security", "target_weight"}
    if not required <= set(weights.columns):
        # Backward-compatible legacy wide weights: index is the signal date and
        # columns are securities.  The new long artifact remains the only form
        # written by this bridge.
        wide = weights.copy()
        wide.index.name = "signal_date"
        weights = wide.reset_index().melt(id_vars=["signal_date"], var_name="security", value_name="target_weight")
        weights["effective_date"] = pd.to_datetime(weights["signal_date"]) + pd.Timedelta(days=1)
    if not required <= set(weights.columns):
        raise ValueError(f"Target Weight requires columns: {sorted(required)}")
    if (weights.target_weight.isna() | ~weights.target_weight.map(lambda x: pd.notna(x) and float(x) >= 0)).any():
        raise ValueError("Target Weight contains invalid target_weight")
    if (weights.groupby("effective_date").target_weight.sum() > 1.0000001).any():
        raise ValueError("Target Weight exceeds 100% on an effective date")
    weights.sort_values(["effective_date", "security"]).to_csv(weights_csv, index=False)
    code = build_effective_weight_strategy(weights_csv, etf_raw=fq == "none")
    return run_unified_backtest(
        run_id,
        {
            "code": code,
            "start_date": start_date,
            "end_date": end_date,
            "initial_cash": initial_cash,
            "frequency": "day",
            "benchmark": benchmark,
            "fq": fq,
            "release_id": release_id,
            "extras": dict(extras or {}),
            "strategy_name": "Kronos TopK Equal Weight v1",
        },
        runs_dir=os.fspath(root),
    )
