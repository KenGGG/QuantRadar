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
    from quantradar.qml import run_qlib_loop  # noqa: F401

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


# 2) Dolt 可达才运行（否则 skip）；统一用 requires_dolt 标记，与 conftest 自动 skip 一致
pytestmark = [
    pytest.mark.requires_dolt,
    pytestmark,
    pytest.mark.skipif(not _dolt_reachable(), reason="investment_data(Dolt) 不可达：跳过 Qlib 闭环测试"),
]


def test_qml_closed_loop_small():
    """小配置跑通 loop→bridge 闭环，并断言无未来函数与无仓库污染。

    复用共享 qlib 目录（单目录/进程，与真实用法一致）。关键：共享目录只构建一次、只读取，
    任何测试都**不重建**它——qlib 的 InstrumentProvider/CalendarProvider 缓存不随 provider_uri
    重定向失效，同进程内切换/重建 qlib_data_dir 会读到陈旧 instruments，破坏数据正确性。
    dump 的正确性由 test_dump_qlib_data（只读校验目录结构）覆盖。
    """
    from quantradar.qml import run_qlib_loop, run_target_weight_backtest
    from tests.unit._qml_helpers import build_shared_qlib_dir

    qlib_dir = build_shared_qlib_dir()
    cwd_before = os.getcwd()
    try:
        loop_result = run_qlib_loop(
            qlib_dir, start="2020-01-01", end="2021-12-31",
            topk=4, num_boost_round=30, early_stopping_rounds=8, model="lgb",
        )
        weights = loop_result["weights"]
        engine, snap = run_target_weight_backtest(
            weights, start_date="2021-07-01", end_date="2021-12-31", initial_cash=1_000_000.0,
        )
    finally:
        # 断言：仓库根（cwd）未生成 ./mlruns（防污染，exp_manager 已重定向临时目录）
        assert not os.path.exists(os.path.join(cwd_before, "mlruns")), "仓库根出现 ./mlruns 污染"

    loop = {
        "feature_dim": loop_result["feature_dim"],
        "ic_mean": loop_result["ic_mean"],
        "rankic_mean": loop_result["rankic_mean"],
        "weights_rows": int(weights.shape[0]) if not weights.empty else 0,
        "weights_cols": int(weights.shape[1]) if not weights.empty else 0,
    }
    dump_instruments = _shared_instrument_count(qlib_dir)

    # 1) loop 阶段：IC/RankIC 为有限数；Alpha158 特征维度；Target Weight 形状合理
    assert loop["feature_dim"] == 158, "Alpha158 特征维度应为 158"
    import math

    assert math.isfinite(loop["ic_mean"]), "IC 应为有限数"
    assert math.isfinite(loop["rankic_mean"]), "RankIC 应为有限数"
    assert abs(loop["ic_mean"]) < 1.0, "IC 应在 [-1,1]"
    assert abs(loop["rankic_mean"]) < 1.0, "RankIC 应在 [-1,1]"
    assert loop["weights_rows"] > 0
    # 列数 = 各测试日 Top-K 出现过的证券并集，不超过宇宙上限
    assert 0 < loop["weights_cols"] <= dump_instruments, (
        f"weights_cols={loop['weights_cols']} 应 <= 宇宙 {dump_instruments}"
    )

    # 2) bridge 阶段：BulletTrade 真实账户回测产出 NAV/Trades/Positions
    records = snap.get("daily_records") or []
    assert records, "回测未产出 daily_records（NAV）"
    assert snap.get("trades"), "回测未产生任何成交"
    last_value = records[-1].get("total_value")
    assert last_value not in (None, 0), "期末账户总值应为正数"

    # 3) 防未来函数（结构性校验）：测试窗口严格晚于训练+验证
    assert loop_result["test_start"] >= "2021-07-01", "测试窗口应处于时间轴最末（防泄漏）"
    assert loop_result["test_end"] <= "2021-12-31"


def _shared_instrument_count(qlib_dir: str) -> int:
    """读共享目录 instruments/all.txt 的证券数（只读，不重建）。"""
    path = os.path.join(qlib_dir, "instruments", "all.txt")
    n = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def test_dump_qlib_data():
    """（只读）校验共享 qlib 目录的 dump 产出结构正确：calendar / instruments / features。"""
    from tests.unit._qml_helpers import build_shared_qlib_dir

    qlib_dir = build_shared_qlib_dir()
    # calendar
    cal_path = os.path.join(qlib_dir, "calendars", "day.txt")
    assert os.path.isfile(cal_path), "缺 calendars/day.txt"
    with open(cal_path, encoding="utf-8") as f:
        cal_days = sum(1 for ln in f if ln.strip())
    assert cal_days > 0, "交易日历为空"

    # instruments
    inst_count = _shared_instrument_count(qlib_dir)
    assert 0 < inst_count <= 20, f"证券数异常：{inst_count}"

    # features：每个证券 7 个字段（见 dump._QLIB_FIELDS）
    feat_dir = os.path.join(qlib_dir, "features")
    assert os.path.isdir(feat_dir), "缺 features 目录"
    bin_files = []
    for _root, _dirs, _files in os.walk(feat_dir):
        bin_files.extend(_files)
    assert len(bin_files) == inst_count * 7, (
        f"特征文件数 {len(bin_files)} 应 = 证券数 {inst_count} × 7 字段"
    )


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
