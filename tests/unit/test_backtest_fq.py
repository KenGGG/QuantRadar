"""复权口径配置与审计（T1）。

调研结论：investment_data 的 final_a_stock_eod_price.close/open/high/low 已是连续复权价
（分红 / 送转缺口已消除），故回测腿（读 final.close）与 Qlib 训练（读 final.adjclose）天然
同源连续复权价，除权日均无假跳变。本测试固化：
  - run_backtest 的 fq 参数正确透传到 snapshot config（审计口径）。
  - 无论 fq='none' 还是 fq='pre'，回测净值连续、无除权假跳变（数据源已复权）。
  - fq 切换安全：none 与 pre 在 final 表上回测收益率一致（仅绝对水平缩放，期末对齐）。
"""
from __future__ import annotations

import pandas as pd
import pytest

from quantradar.backtest import run_backtest

pytestmark = pytest.mark.requires_dolt

SECURITY = "600519.XSHG"
START = "2023-01-03"
END = "2024-12-31"
CASH = 500000.0
AMOUNT = 290  # 满仓放大信号，便于稳健断言


def _nav(snapshot):
    records = snapshot.get("daily_records") or []
    return [float(r["total_value"]) for r in records if r.get("total_value") is not None]


def _daily_returns(vals):
    if len(vals) < 2:
        return pd.Series(dtype=float)
    return pd.Series(vals).pct_change().dropna()


def test_backtest_fq_recorded_in_config():
    """fq 参数透传到 snapshot.config，供审计与复现。"""
    _, snap_none = run_backtest(
        security=SECURITY, start_date=START, end_date=END,
        initial_cash=CASH, amount=AMOUNT, fq="none",
    )
    _, snap_pre = run_backtest(
        security=SECURITY, start_date=START, end_date=END,
        initial_cash=CASH, amount=AMOUNT, fq="pre",
    )
    assert snap_none["config"]["fq"] == "none"
    assert snap_pre["config"]["fq"] == "pre"
    assert len(snap_none["daily_records"]) > 100
    assert len(snap_pre["daily_records"]) > 100


def test_backtest_nav_continuous_no_exrights_jump():
    """回测腿净值连续：数据源 final 表已是复权价，除权日无假跳变。"""
    _, snap = run_backtest(
        security=SECURITY, start_date=START, end_date=END,
        initial_cash=CASH, amount=AMOUNT, fq="none",
    )
    rets = _daily_returns(_nav(snap))
    assert not rets.empty
    # 单日最大绝对变动应落在真实市场波动范围（排除除权假跳变，如 <-30% 的缺口）
    assert rets.abs().max() < 0.30


def test_backtest_fq_none_and_pre_equivalent():
    """fq 切换安全：final 表已复权，none 与 pre 回测收益率一致（期末对齐 <1%）。"""
    _, snap_none = run_backtest(
        security=SECURITY, start_date=START, end_date=END,
        initial_cash=CASH, amount=AMOUNT, fq="none",
    )
    _, snap_pre = run_backtest(
        security=SECURITY, start_date=START, end_date=END,
        initial_cash=CASH, amount=AMOUNT, fq="pre",
    )
    v_none = pd.Series(_nav(snap_none))
    v_pre = pd.Series(_nav(snap_pre))
    rn = v_none.pct_change().dropna()
    rp = v_pre.pct_change().dropna()
    corr = rn.corr(rp)
    assert corr > 0.999, f"none 与 pre 回测收益率相关性过低: {corr}"
    # 期末对齐（前复权基准=期末，期末价=原始价）
    rel = abs(v_none.iloc[-1] - v_pre.iloc[-1]) / v_none.iloc[-1]
    assert rel < 0.01, f"none 与 pre 期末未对齐: rel_diff={rel}"
