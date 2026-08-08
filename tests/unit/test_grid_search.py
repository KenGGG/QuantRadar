"""T3 网格寻优单元测试（RESEARCH_T3_GRID）。

覆盖：grid_search_qlib 在固定种子下遍历超参组合、按 IC 选优、结果可复现（同输入同输出）。

环境：需要 qlib + lightgbm + 可达 investment_data（requires_dolt）。
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.requires_dolt

try:
    import qlib  # noqa: F401
    import lightgbm  # noqa: F401

    from quantradar.qml import grid_search_qlib

    _HAVE_QLIB = True
except Exception:  # pragma: no cover - 依赖可选
    _HAVE_QLIB = False

pytestmark = [
    pytestmark,
    pytest.mark.skipif(not _HAVE_QLIB, reason="qlib/lightgbm 不可用：跳过网格寻优测试"),
]


def _build_small_qlib() -> str:
    # 共享同一 qlib 目录，避免跨函数触发 provider_uri 重定向（详见 _qml_helpers）。
    from tests.unit._qml_helpers import build_shared_qlib_dir

    return build_shared_qlib_dir()


def test_grid_search_runs_and_selects_best():
    """网格寻优应产出全部组合结果，并按 IC 选出 best_params。"""
    d = _build_small_qlib()
    grid = {"learning_rate": [0.05, 0.1], "num_leaves": [31, 63]}
    res = grid_search_qlib(
        d, "2020-01-01", "2021-12-31", model="lgb", param_grid=grid,
        topk=4, num_boost_round=30, early_stopping_rounds=8,
    )
    assert len(res["results"]) == 4, "2x2 网格应产出 4 组结果"
    for r in res["results"]:
        assert set(r["params"].keys()) == {"learning_rate", "num_leaves"}
    # 至少一组 IC 有限，且 best 来自有限 IC 组
    import math

    finite = [r for r in res["results"] if math.isfinite(r["ic_mean"])]
    assert finite, "应至少有一组有限 IC"
    assert res["best_params"] is not None
    assert res["best_ic"] == max(r["ic_mean"] for r in finite)


def test_grid_search_deterministic():
    """固定 seed：相同输入两次运行结果应完全一致（可复现）。"""
    d = _build_small_qlib()
    grid = {"learning_rate": [0.05, 0.1], "num_leaves": [31, 63]}
    a = grid_search_qlib(d, "2020-01-01", "2021-12-31", model="lgb", param_grid=grid, num_boost_round=30, early_stopping_rounds=8)
    b = grid_search_qlib(d, "2020-01-01", "2021-12-31", model="lgb", param_grid=grid, num_boost_round=30, early_stopping_rounds=8)
    assert [r["params"] for r in a["results"]] == [r["params"] for r in b["results"]]
    assert [r["ic_mean"] for r in a["results"]] == [r["ic_mean"] for r in b["results"]]
    assert a["best_params"] == b["best_params"]
