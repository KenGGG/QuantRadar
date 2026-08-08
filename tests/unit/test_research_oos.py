"""T4 样本外稳健性验证单元测试（RESEARCH_T4_OOS）。

覆盖：run_research_oos 产出结构化（JSON 可序列化）报告、字段齐全、样本外 IC 有限、
可复现（同输入同输出）。端到端调用 grid_search_qlib + walk_forward_qlib（真实 Alpha158+LGBModel）。

环境：需要 qlib + lightgbm + 可达 investment_data（requires_dolt）。
"""

from __future__ import annotations

import json
import math

import pytest

pytestmark = pytest.mark.requires_dolt

try:
    import qlib  # noqa: F401
    import lightgbm  # noqa: F401

    from quantradar.qml import run_research_oos

    _HAVE_QLIB = True
except Exception:  # pragma: no cover - 依赖可选
    _HAVE_QLIB = False

pytestmark = [
    pytestmark,
    pytest.mark.skipif(not _HAVE_QLIB, reason="qlib/lightgbm 不可用：跳过样本外验证测试"),
]


def _run(qlib_dir):
    from quantradar.qml.loop import grid_search_qlib  # 仅用于参数网格形状一致

    return run_research_oos(
        qlib_dir, "2020-01-01", "2022-12-31", model="lgb",
        topk=4, train_years=1, valid_months=3, test_months=3, step_months=6,
        seed=42, num_boost_round=30, early_stopping_rounds=8,
        do_grid=True,
        param_grid={"learning_rate": [0.05, 0.1], "num_leaves": [31, 63]},
    )


def test_oos_report_fields_and_finite():
    """报告应包含 config/grid/folds/oos/environment，且样本外 IC 有限、折数>=1。"""
    from tests.unit._qml_helpers import build_shared_qlib_dir

    rep = _run(build_shared_qlib_dir())
    for key in ("config", "grid", "folds", "oos", "environment"):
        assert key in rep, f"报告缺少 {key}"
    assert rep["oos"]["n_folds"] >= 1, "应至少产出一个样本外折"
    assert math.isfinite(rep["oos"]["mean_ic"]), "平均样本外 IC 应为有限数"
    assert math.isfinite(rep["oos"]["mean_rankic"]), "平均样本外 RankIC 应为有限数"
    # grid 选优结果存在
    assert rep["grid"] is not None
    assert rep["grid"]["n_combos"] >= 1
    # 每折记录完整
    for f in rep["folds"]:
        assert {"fold", "segments", "ic_mean", "rankic_mean", "train_samples", "feature_dim"} <= set(f)
        assert math.isfinite(f["ic_mean"]), f"折 {f['fold']} IC 应为有限数"


def test_oos_report_reproducible():
    """固定 seed：相同输入两次运行应产出一致的 JSON 报告（可复现）。"""
    from tests.unit._qml_helpers import build_shared_qlib_dir

    d = build_shared_qlib_dir()
    a = _run(d)
    b = _run(d)
    # JSON 序列化后逐字节比较（numpy 标量已转为 python 原生类型）
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a["oos"]["mean_ic"] == b["oos"]["mean_ic"]
