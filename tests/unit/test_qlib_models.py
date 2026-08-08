"""T3 多模型可用性探测单元测试（RESEARCH_T3_MULTIMODEL）。

覆盖：available_models 探测、未知模型 ValueError、已知但缺失依赖 NotImplementedError（不伪造）、
run_qlib_loop 支持 model 选择（lgb 必可用；xgb/mlp 按环境探测）。

环境：需要 qlib + lightgbm（lgb 为本环境唯一可用模型）；需要可达的 investment_data（requires_dolt）。
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.requires_dolt

try:
    import qlib  # noqa: F401
    import lightgbm  # noqa: F401

    from quantradar.qml import available_models, run_qlib_loop

    _HAVE_QLIB = True
except Exception:  # pragma: no cover - 依赖可选
    _HAVE_QLIB = False

pytestmark = [
    pytestmark,
    pytest.mark.skipif(not _HAVE_QLIB, reason="qlib/lightgbm 不可用：跳过多模型测试"),
]


def _build_small_qlib() -> str:
    # 共享同一 qlib 目录，避免跨函数触发 provider_uri 重定向（详见 _qml_helpers）。
    from tests.unit._qml_helpers import build_shared_qlib_dir

    return build_shared_qlib_dir()


def test_lgb_always_available():
    """lgb 应始终在可用模型列表中（本环境 lightgbm 已装）。"""
    assert "lgb" in available_models()


def test_unknown_model_raises_valueerror():
    from quantradar.qml.loop import _get_model_class

    with pytest.raises(ValueError):
        _get_model_class("not_a_model")


def test_unavailable_model_raises_notimplemented():
    """已知但当前环境缺失依赖的模型应抛 NotImplementedError，绝不伪造。"""
    from quantradar.qml.loop import _get_model_class

    avail = set(available_models())
    for m in ("xgb", "mlp"):
        if m not in avail:
            with pytest.raises(NotImplementedError):
                _get_model_class(m)


def test_run_qlib_loop_lgb_runs():
    """run_qlib_loop(model='lgb') 应能跑通并产出有限 IC。"""
    d = _build_small_qlib()
    out = run_qlib_loop(d, "2020-01-01", "2021-12-31", topk=4, num_boost_round=30, early_stopping_rounds=8, model="lgb")
    import math

    assert math.isfinite(out["ic_mean"]), "IC 应为有限数"
    assert math.isfinite(out["rankic_mean"]), "RankIC 应为有限数"
    assert out["feature_dim"] == 158, "Alpha158 特征维度应为 158"
    assert out["weights"].shape[0] > 0, "应产出 Target Weight"
