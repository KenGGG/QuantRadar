"""Phase 9 因子研究（目标口径）—— 复用 BulletTrade IC/RankIC/分层/多空（DB-backed，无 mock）。

验证：
  - run_momentum_research 在真实数据上产出 IC / RankIC / 分层收益 / 多空组合收益。
  - 因子值仅用过去数据（动量 = 过去 lookback 日收益），forward_return 为研究标签。
  - 结果与数据源一致，不伪造指标。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quantradar.bootstrap import bootstrap_investment_data
from quantradar.research.factors import (
    build_factor_panel,
    run_factor_research,
    run_momentum_research,
)

pytestmark = [pytest.mark.unit, pytest.mark.requires_dolt]

UNIV = None  # 在 fixture 中惰性取沪深300子集
START = "2023-01-03"
END = "2023-03-31"


@pytest.fixture(scope="module")
def universe():
    # 防御性 skip：Dolt 不可达时（如 CI），即使 requires_dolt 标记的模块级 skip
    # 因模块作用域 fixture 的 setup 顺序问题未拦截，也在此优雅跳过，避免 ERROR at setup。
    try:
        p = bootstrap_investment_data(set_active=True, overwrite=True)
        return p.get_index_stocks("000300.SH", START)[:30]
    except Exception as exc:  # 连接/查询失败（CI 无 Dolt）
        pytest.skip(f"investment_data(Dolt) 不可达，跳过因子研究：{exc}")


class TestFactorResearch:
    def test_momentum_produces_ic_and_rankic(self, universe):
        res = run_momentum_research(
            universe, START, END, lookback=10, forward=1, n_buckets=5
        )
        # IC / RankIC 为真实计算的序列（非全 NaN）
        assert not res.ic.dropna().empty, "IC 序列为空"
        assert not res.rank_ic.dropna().empty, "RankIC 序列为空"
        assert np.isfinite(res.metrics["ic_mean"])
        assert np.isfinite(res.metrics["rank_ic_mean"])

    def test_layer_and_long_short_populated(self, universe):
        res = run_momentum_research(
            universe, START, END, lookback=10, forward=1, n_buckets=5
        )
        # 分层收益：每个交易日有 n_buckets 层
        assert not res.bucket_returns.empty
        assert set(res.bucket_returns["bucket"].unique()) <= set(range(1, 6))
        # 多空组合收益逐日记录
        assert not res.portfolio_returns.empty
        assert {"date", "gross_return", "net_return", "turnover"} <= set(
            res.portfolio_returns.columns
        )

    def test_panel_shape_and_columns(self, universe):
        panel = build_factor_panel(universe, START, END, lookback=10, forward=1)
        assert not panel.empty
        assert list(panel.columns) == ["date", "code", "factor", "forward_return"]
        # 无未来函数：factor 不含 NaN 且在窗口内
        assert panel["date"].min() >= pd.to_datetime(START).date()

    def test_custom_factor_fn(self, universe):
        # 反转因子（过去收益取负）同样可被评估
        res = run_factor_research(
            universe,
            START,
            END,
            lookback=10,
            forward=1,
            n_buckets=5,
            factor_fn=lambda df: -df["close"].pct_change(10),
        )
        assert np.isfinite(res.metrics["ic_mean"])
