"""T3 walk-forward 滚动窗口单元测试（RESEARCH_T3_WALKFORWARD）。

覆盖：walk_forward_qlib 逐折训练/验证/测试、各折 segments 不重叠（防泄漏）、样本外 IC 可复现。

环境：需要 qlib + lightgbm + 可达 investment_data（requires_dolt）。
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.requires_dolt

try:
    import qlib  # noqa: F401
    import lightgbm  # noqa: F401

    from quantradar.qml import walk_forward_qlib
    from quantradar.qml.loop import assert_segments_disjoint

    _HAVE_QLIB = True
except Exception:  # pragma: no cover - 依赖可选
    _HAVE_QLIB = False

pytestmark = [
    pytestmark,
    pytest.mark.skipif(not _HAVE_QLIB, reason="qlib/lightgbm 不可用：跳过 walk-forward 测试"),
]


def _build_small_qlib() -> str:
    # 共享同一 qlib 目录，避免跨函数触发 provider_uri 重定向（详见 _qml_helpers）。
    from tests.unit._qml_helpers import build_shared_qlib_dir

    return build_shared_qlib_dir()


def test_walk_forward_produces_folds():
    """walk-forward 应产出至少一个样本外折，每折 IC 有限且内部 segments 不重叠。"""
    d = _build_small_qlib()
    out = walk_forward_qlib(
        d, "2020-01-01", "2022-12-31", model="lgb",
        topk=4, train_years=1, valid_months=3, test_months=3, step_months=6,
        num_boost_round=30, early_stopping_rounds=8,
    )
    import math

    assert out["n_folds"] >= 1, "应至少产出一个折"
    for f in out["folds"]:
        # 内部防泄漏守卫：若重叠，_fit_predict 内的 assert_segments_disjoint 会抛错使测试失败
        assert_segments_disjoint(f["segments"])
        assert math.isfinite(f["ic_mean"]), f"折 {f['fold']} IC 应为有限数"
        # 每折 test 区间应在总窗口内
        assert f["segments"]["test"][1] <= "2022-12-31"


def test_walk_forward_deterministic():
    """固定 seed：相同输入两次运行折数与首折 IC 应一致（可复现）。"""
    d = _build_small_qlib()
    common = dict(
        start="2020-01-01", end="2022-12-31", model="lgb", topk=4,
        train_years=1, valid_months=3, test_months=3, step_months=6,
        num_boost_round=30, early_stopping_rounds=8,
    )
    a = walk_forward_qlib(d, **common)
    b = walk_forward_qlib(d, **common)
    assert a["n_folds"] == b["n_folds"] > 0
    assert a["folds"][0]["ic_mean"] == b["folds"][0]["ic_mean"]
