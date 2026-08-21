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


def build_effective_weight_strategy(weights_csv: str | Path) -> str:
    return f'''# QuantRadar: effective-dated Target Weight -> BulletTrade
import pandas as pd

_WEIGHTS = pd.read_csv(r"{Path(weights_csv).resolve()}", index_col=0, parse_dates=True)
_LAST_APPLIED = None

def _rebalance(context):
    global _LAST_APPLIED
    day = pd.Timestamp(context.current_dt).normalize()
    eligible = _WEIGHTS.index[_WEIGHTS.index <= day]
    if eligible.empty:
        return
    effective_date = eligible[-1]
    if _LAST_APPLIED is not None and effective_date <= _LAST_APPLIED:
        return
    row = _WEIGHTS.loc[effective_date]
    total = context.portfolio.total_value
    targets = set()
    for security, weight in row.items():
        if pd.notna(weight) and float(weight) > 0:
            order_target_value(security, float(weight) * total)
            targets.add(security)
    for security in list(context.portfolio.positions.keys()):
        if security not in targets:
            order_target_value(security, 0.0)
    _LAST_APPLIED = effective_date

def initialize(context):
    pass

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
    runs_dir: str | Path | None = None,
    extras: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if weights is None or weights.empty:
        raise ValueError("Target Weight is empty")
    root = Path(runs_dir) if runs_dir is not None else Path.cwd() / "runs"
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    weights_csv = run_dir / "target_weights.csv"
    weights.sort_index().to_csv(weights_csv)
    code = build_effective_weight_strategy(weights_csv)
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
            "extras": dict(extras or {}),
            "strategy_name": "Kronos TopK Equal Weight v1",
        },
        runs_dir=os.fspath(root),
    )
