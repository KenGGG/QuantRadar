from __future__ import annotations

import pandas as pd
import pytest

from quantradar.kronos.portfolio import (
    build_topk_target_weights,
    target_weight_hash,
    to_wide_weights,
)


def _signals() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "signal_run_id": ["sig"] * 4,
            "signal_date": ["2022-06-24"] * 4,
            "execution_date": ["2022-06-27"] * 4,
            "security": ["B", "A", "C", "D"],
            "pred_return": [0.2, 0.2, 0.1, None],
            "eligible": [True, True, True, True],
            "prediction_hash": ["pred"] * 4,
        }
    )


def test_topk_uses_security_tie_break_and_equal_weights():
    weights = build_topk_target_weights(_signals(), topk=2)
    assert weights["security"].tolist() == ["A", "B"]
    assert weights["rank"].tolist() == [1, 2]
    assert weights["target_weight"].tolist() == [0.5, 0.5]
    assert weights["target_weight"].sum() == 1.0
    assert weights["strategy_version"].unique().tolist() == ["kronos_topk_equal_weight_v1"]


def test_fewer_than_topk_still_sums_to_one_and_pivots():
    weights = build_topk_target_weights(_signals().iloc[:1], topk=20)
    assert weights["target_weight"].tolist() == [1.0]
    wide = to_wide_weights(weights)
    assert wide.index.astype(str).tolist() == ["2022-06-27"]
    assert wide.loc[pd.Timestamp("2022-06-27"), "B"] == 1.0
    assert target_weight_hash(weights) == target_weight_hash(weights.copy())


def test_portfolio_rejects_same_day_execution_and_nonpositive_topk():
    same_day = _signals()
    same_day["execution_date"] = same_day["signal_date"]
    with pytest.raises(ValueError, match="strictly later"):
        build_topk_target_weights(same_day, topk=2)
    with pytest.raises(ValueError, match="topk must be positive"):
        build_topk_target_weights(_signals(), topk=0)
