"""Target Weight → BulletTrade 账户回测桥接。

把 Qlib 预测出的 Target Weight（DataFrame：index=交易日、columns=证券(JQ代码)、values=权重）
落到一个 JoinQuant 兼容策略里：每月第 1 个交易日按目标权重再平衡
（order_target_value(security, weight * total_value)），不在目标内的持仓清零。

复用现有 backtest.run_backtest（BulletTrade 撮合/账户/下单均来自 BulletTrade，禁止重实现）。
权重表写入临时 CSV，策略源码在运行时读取，避免把大表嵌入源码。
"""

from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from quantradar.backtest import run_backtest
from quantradar.portfolio.target_weight_bridge import build_monthly_signal_weight_strategy


def select_signal_date(weights_index: Any, day: Any) -> Optional[pd.Timestamp]:
    """从权重表交易日索引中，选取「严格早于」交易执行日 day 的最新信号日。

    防未来函数核心：T 日 09:30 调仓时，只能使用 T 日之前（不含 T）收盘产生的信号，
    T 日信号须留到 T+1 交易。返回 None 表示尚无可用的历史信号。
    """
    idx = pd.DatetimeIndex(weights_index)
    day = pd.Timestamp(day).normalize()
    mask = idx < day  # 严格早于，杜绝同日信号前视
    if not mask.any():
        return None
    return idx[mask][-1]


def _build_strategy_source(weights_csv: str) -> str:
    """生成读取权重表并按月再平衡的策略源码。

    关键：再平衡在 T 日 09:30 触发，但只取「严格早于 T」的最新信号（T 日信号留到 T+1），
    杜绝同日未来数据泄露（look-ahead bias）。
    """
    return build_monthly_signal_weight_strategy(weights_csv)


def run_target_weight_backtest(
    weights: pd.DataFrame,
    start_date: str,
    end_date: str,
    initial_cash: float = 1_000_000.0,
    fq: str = "pre",
) -> Tuple[Any, Dict[str, Any]]:
    """用 Target Weight 在 BulletTrade 上跑账户回测，返回 (engine, snapshot)。

    Args:
        weights: Target Weight DataFrame（index=交易日, columns=JQ代码, values=权重）。
        start_date/end_date: 回测区间（应为权重覆盖的测试期）。
        initial_cash: 初始资金。
        fq: 复权口径。默认 'pre'（连续前复权），与 Qlib 训练所用的后复权(hfq)在同一窗口内
            收益率等价（仅净值绝对水平缩放常数因子），使模型预测收益与账户实现收益口径一致、
            除权日无假跳变。若需真实现金流水归因可显式传 'none'。
    """
    if weights is None or weights.empty:
        raise ValueError("Target Weight 为空，无法回测")
    if (fq or "none").lower() not in ("none", "pre", "qfq", "post", "hfq"):
        raise ValueError(
            f"run_target_weight_backtest: 不支持的复权方式 fq={fq!r}"
        )

    tmp_dir = tempfile.mkdtemp(prefix="qr_tw_")
    weights_csv = os.path.join(tmp_dir, "target_weights.csv")
    # 列名已是 JQ 代码（600519.XSHG），直接写出
    weights.to_csv(weights_csv)

    code = _build_strategy_source(weights_csv)
    engine, snapshot = run_backtest(
        code=code,
        start_date=start_date,
        end_date=end_date,
        initial_cash=initial_cash,
        frequency="day",
        fq=fq,
    )
    return engine, snapshot
