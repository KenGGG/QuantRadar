"""因子研究（Phase 9 因子研究）—— 复用 BulletTrade 的 IC / RankIC / 分层 / 多空。

数据源：InvestmentDataProvider（真实 investment_data）。所有因子均由真实行情推导，
绝不使用 adjclose 冒充原始价，且因子值仅用「当时可得」的过去数据（防未来函数）。

核心复用：bullet_trade.research.factors.evaluation.evaluate_factor_performance
  - 输入长表：columns = [date, code, <factor_col>, <return_col>]
  - 输出：IC / RankIC 序列、分层收益（bucket_returns）、多空组合收益、汇总指标。

典型用法（动量因子）：
    from quantradar.research.factors import run_momentum_research
    res = run_momentum_research(
        universe=["600519.XSHG", "000001.XSHE"],
        start_date="2023-01-01", end_date="2023-12-31", lookback=20, forward=1)
    print(res.metrics["ic_mean"], res.metrics["rank_ic_mean"])
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Callable, Dict, List, Optional, Sequence

import pandas as pd

from bullet_trade.research.factors.evaluation import (
    BacktestConfig,
    CostConfig,
    EvaluationResult,
    evaluate_factor_performance,
)

from ..bootstrap import bootstrap_investment_data
from ..providers.investment_data.symbols import normalize_stock_symbol


def _jw_to_internal(code: str) -> str:
    return normalize_stock_symbol(code)


def _single_security_panel(
    provider,
    code: str,
    start: str,
    end: str,
    lookback: int,
    forward: int,
) -> pd.DataFrame:
    """对单只标的构建 [date, factor(动量), forward_return] 长表行（仅用过去数据算因子）。"""
    # 多取 lookback+forward 日，确保窗口首日也能算出因子与前瞻收益
    pad_start = (pd.to_datetime(start) - timedelta(days=(lookback + forward) * 2)).strftime(
        "%Y-%m-%d"
    )
    df = provider.get_price(code, start_date=pad_start, end_date=end, fields=["close"])
    if df is None or df.empty or len(df) <= lookback:
        return pd.DataFrame(columns=["date", "factor", "forward_return"])

    closes = df["close"].astype(float)
    # 动量因子：过去 lookback 日收益率（仅用截至当日的过去数据）
    factor = closes.pct_change(lookback)
    # 前瞻收益：未来 forward 日收益率（研究标签，非回测信号）
    fwd = closes.pct_change(forward).shift(-forward)

    out = pd.DataFrame(
        {
            "date": df.index,
            "factor": factor.values,
            "forward_return": fwd.values,
        }
    )
    out["code"] = code
    # 截断到请求窗口（pad 只是为了计算因子/前瞻）
    out = out[out["date"] >= pd.to_datetime(start)]
    out = out.dropna(subset=["factor", "forward_return"])
    return out[["date", "code", "factor", "forward_return"]]


def build_factor_panel(
    universe: Sequence[str],
    start_date: str,
    end_date: str,
    lookback: int = 20,
    forward: int = 1,
    provider=None,
) -> pd.DataFrame:
    """构建因子研究长表（date, code, factor, forward_return）。

    因子默认 = 动量（过去 lookback 日收益率）；如需自定义因子，见 run_factor_research(factor_fn=...)。
    """
    provider = provider or bootstrap_investment_data(set_active=True, overwrite=True)
    frames: List[pd.DataFrame] = []
    for code in universe:
        try:
            fr = _single_security_panel(
                provider, code, start_date, end_date, lookback, forward
            )
            if not fr.empty:
                frames.append(fr)
        except Exception:
            # 单标的缺数据不应中断整体研究（显式 PARTIAL）
            continue
    if not frames:
        return pd.DataFrame(columns=["date", "code", "factor", "forward_return"])
    panel = pd.concat(frames, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"]).dt.date
    return panel


def run_factor_research(
    universe: Sequence[str],
    start_date: str,
    end_date: str,
    lookback: int = 20,
    forward: int = 1,
    n_buckets: int = 5,
    long_buckets: Optional[List[int]] = None,
    short_buckets: Optional[List[int]] = None,
    factor_fn: Optional[Callable[[pd.DataFrame], pd.Series]] = None,
    provider=None,
) -> EvaluationResult:
    """对给定股票池运行因子研究，复用 BulletTrade 的 IC/RankIC/分层/多空。

    factor_fn: 可选自定义因子函数，签名 (close_panel: pd.DataFrame[date, close]) -> pd.Series
        （索引=日期，与 close_panel 对齐）。默认使用动量（过去 lookback 日收益率）。
    """
    provider = provider or bootstrap_investment_data(set_active=True, overwrite=True)
    frames: List[pd.DataFrame] = []
    for code in universe:
        pad_start = (
            pd.to_datetime(start_date) - timedelta(days=(lookback + forward) * 2)
        ).strftime("%Y-%m-%d")
        df = provider.get_price(code, start_date=pad_start, end_date=end_date, fields=["close"])
        if df is None or df.empty or len(df) <= lookback:
            continue
        closes = df["close"].astype(float)
        if factor_fn is not None:
            fac = factor_fn(df)
        else:
            fac = closes.pct_change(lookback)
        fwd = closes.pct_change(forward).shift(-forward)
        out = pd.DataFrame(
            {
                "date": df.index,
                "factor": fac.values,
                "forward_return": fwd.values,
            }
        )
        out["code"] = code
        out = out[out["date"] >= pd.to_datetime(start_date)]
        out = out.dropna(subset=["factor", "forward_return"])
        if not out.empty:
            frames.append(out[["date", "code", "factor", "forward_return"]])
        if len(frames) == 0:
            return _empty_evaluation()

    panel = pd.concat(frames, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"]).dt.date

    cfg = BacktestConfig(
        n_buckets=n_buckets,
        long_buckets=long_buckets or list(range(n_buckets, n_buckets + 1)),
        short_buckets=short_buckets or (list(range(1, n_buckets)) if n_buckets > 1 else []),
        factor_col="factor",
        return_col="forward_return",
    )
    return evaluate_factor_performance(panel, cfg, CostConfig())


def run_momentum_research(
    universe: Sequence[str],
    start_date: str,
    end_date: str,
    lookback: int = 20,
    forward: int = 1,
    n_buckets: int = 5,
    provider=None,
) -> EvaluationResult:
    """动量因子研究（默认 lookback=20 日收益率，多空=第 n 层多 / 第 1 层空）。"""
    return run_factor_research(
        universe, start_date, end_date, lookback, forward, n_buckets,
        long_buckets=list(range(n_buckets, n_buckets + 1)),
        short_buckets=list(range(1, 2)) if n_buckets > 1 else None,
        provider=provider,
    )


def _empty_evaluation() -> EvaluationResult:
    return EvaluationResult(
        bucket_returns=pd.DataFrame(),
        ic=pd.Series(dtype="float64"),
        rank_ic=pd.Series(dtype="float64"),
        portfolio_returns=pd.DataFrame(),
        metrics={"ic_mean": float("nan"), "rank_ic_mean": float("nan")},
        meta={},
    )
