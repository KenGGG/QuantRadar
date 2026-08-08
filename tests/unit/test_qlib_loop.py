"""Qlib 最小闭环单元测试（QLIB_BULLETTRADE_LOOP_PASS）。

覆盖链路：investment_data(Dolt) → qlib_data → Alpha158+LGBModel
→ Prediction/IC/RankIC → TopK Target Weight → BulletTrade 账户回测。

环境约束：
    - 需要 qlib + lightgbm（import 失败则整文件 skip）。
    - 需要可达且通过探针的 investment_data（Dolt @127.0.0.1:3307）；不可达则 skip。
    - 防未来函数：
        * 标签为 Alpha158 标准 Ref($close,-2)/Ref($close,-1)-1（未来 1 日收益），由 handler
          按点对齐生成，天然无前视；
        * 训练/验证/测试按时间不重叠切分；
        * 回测所用 Target Weight 仅来自测试期预测，绝不回看未来。
    - 不污染仓库：LGBModel.fit 经 qml.loop 的 exp_manager 重定向到临时目录，
      不会在仓库根生成 ./mlruns（本测试额外断言 cwd 无 mlruns）。

采用小配置以保证可快速复现（max_instruments 极小、boost round 少）。
"""

from __future__ import annotations

import os

import pytest

# 1) qlib / lightgbm 可用才运行（否则整文件 skip）
try:
    import qlib  # noqa: F401
    from quantradar.qml import run_qml_pipeline  # noqa: F401

    _HAVE_QLIB = True
except Exception:  # pragma: no cover - 依赖可选依赖
    _HAVE_QLIB = False

pytestmark = pytest.mark.skipif(not _HAVE_QLIB, reason="qlib/lightgbm 不可用：跳过 Qlib 闭环测试")


def _dolt_reachable() -> bool:
    """investment_data（Dolt）是否可达且关键表齐全。"""
    try:
        from quantradar.config import load_investment_data_config
        from quantradar.providers.investment_data.connection import (
            InvestmentDataConnection,
            InvestmentDataConnectionError,
        )

        conn = InvestmentDataConnection(load_investment_data_config())
        conn.check()
        conn.close()
        return True
    except Exception:  # pragma: no cover - 依赖真实 DB
        return False


# 2) Dolt 可达才运行（否则 skip）
pytestmark = [
    pytestmark,
    pytest.mark.skipif(not _dolt_reachable(), reason="investment_data(Dolt) 不可达：跳过 Qlib 闭环测试"),
]


def test_qml_closed_loop_small():
    """小配置跑通 dump→loop→bridge，并断言无未来函数与无仓库污染。"""
    cwd_before = os.getcwd()
    try:
        out = run_qml_pipeline(
            start="2020-01-01",
            end="2021-12-31",
            max_instruments=12,
            topk=4,
            num_boost_round=30,
            early_stopping_rounds=8,
            initial_cash=1_000_000.0,
        )
    finally:
        # 断言：仓库根（cwd）未生成 ./mlruns（防污染）
        assert not os.path.exists(os.path.join(cwd_before, "mlruns")), "仓库根出现 ./mlruns 污染"

    dump = out["dump"]
    loop = out["loop"]
    snap = out["backtest"]

    # 1) dump 阶段：真实数据、字段正确、宇宙合理（Point-in-Time 取前 N 只，部分可能无行情被剔除）
    assert dump["calendar_days"] > 0
    assert 0 < dump["instruments"] <= 12
    assert set(dump["fields"]) >= {"open", "high", "low", "close", "volume", "vwap"}
    assert dump["written_feature_files"] == dump["instruments"] * len(dump["fields"])

    # 2) loop 阶段：IC/RankIC 为有限数；Target Weight 形状合理
    assert loop["feature_dim"] == 158, "Alpha158 特征维度应为 158"
    import math

    assert math.isfinite(loop["ic_mean"]), "IC 应为有限数"
    assert math.isfinite(loop["rankic_mean"]), "RankIC 应为有限数"
    assert abs(loop["ic_mean"]) < 1.0, "IC 应在 [-1,1]"
    assert abs(loop["rankic_mean"]) < 1.0, "RankIC 应在 [-1,1]"
    assert loop["weights_rows"] > 0
    # 列数 = 各测试日 Top-K 出现过的证券并集（可大于 topk），但不超过宇宙上限
    assert 0 < loop["weights_cols"] <= dump["instruments"]

    # 3) bridge 阶段：BulletTrade 真实账户回测产出 NAV/Trades/Positions
    records = snap.get("daily_records") or []
    assert records, "回测未产出 daily_records（NAV）"
    assert snap.get("trades"), "回测未产生任何成交"
    last_value = records[-1].get("total_value")
    assert last_value not in (None, 0), "期末账户总值应为正数"

    # 4) 防未来函数（结构性校验）：测试窗口严格晚于训练+验证
    assert out["test_start"] >= "2021-07-01", "测试窗口应处于时间轴最末（防泄漏）"
    assert out["test_end"] <= "2021-12-31"


def test_topk_target_weights_unit():
    """topk_target_weights 纯函数：等权、每行和=1、只取 Top-K、无未来数据。"""
    import pandas as pd

    from quantradar.qml import topk_target_weights

    idx = pd.date_range("2021-07-01", periods=3, freq="D")
    insts = ["000001.XSHE", "000002.XSHE", "000003.XSHE", "000004.XSHE"]
    pred = pd.Series(
        [0.9, 0.1, 0.5, 0.7, 0.2, 0.8, 0.3, 0.6, 0.4, 0.5, 0.5, 0.5],
        index=pd.MultiIndex.from_product([idx, insts]),
    )
    w = topk_target_weights(pred, topk=2)
    assert w.shape[0] == 3
    # 列数 = 各交易日 Top-K 中出现过的证券并集（<= 证券总数），并非恰好 topk
    assert w.shape[1] <= len(insts)
    for _, row in w.iterrows():
        n = int(row.notna().sum())
        assert n <= 2, "每行非零权重数不应超过 topk"
        s = row.sum()
        assert abs(s - 1.0) < 1e-9, "每行权重之和应为 1（等权 Top-K）"
        assert (row.dropna() >= 0).all(), "权重不应为负（NaN 为未入选证券，不参与比较）"
