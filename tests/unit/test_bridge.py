"""Qlib -> BulletTrade 桥接的防未来函数单元测试（Hardening#56）。

聚焦「同日信号前视」这一核心正确性风险：T 日 09:30 调仓只能使用严格早于 T 的信号。
纯函数 select_signal_date 不依赖 Dolt/qlib，可独立验证。
"""

from __future__ import annotations

import pandas as pd

from quantradar.qml.bridge import select_signal_date
from quantradar.qml.loop import assert_segments_disjoint


def _idx(*dates: str) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime(list(dates)))


def test_selects_strictly_before_trade_day():
    idx = _idx("2021-06-28", "2021-06-29", "2021-06-30", "2021-07-01")
    # 在 07-01 调仓，应取 06-30 的信号（严格早于，不能用 07-01 自身）
    assert select_signal_date(idx, "2021-07-01") == pd.Timestamp("2021-06-30")


def test_no_signal_before_first_date_returns_none():
    idx = _idx("2021-07-01", "2021-07-02")
    # 在第一条信号日当天调仓，尚无更早信号 -> None（不会用同日信号）
    assert select_signal_date(idx, "2021-07-01") is None


def test_selects_latest_available_prior():
    idx = _idx("2021-06-01", "2021-06-15", "2021-06-30")
    # 07-10 调仓，应取 06-30（最新早于 07-10 的信号）
    assert select_signal_date(idx, "2021-07-10") == pd.Timestamp("2021-06-30")


def test_timestamp_normalization():
    idx = _idx("2021-06-30")
    # 即使传入带时分秒的 datetime，也应归一化并按日期比较
    assert select_signal_date(idx, "2021-07-01 09:30:00") == pd.Timestamp("2021-06-30")


def test_segments_disjoint_ok():
    segs = {
        "train": ("2020-01-01", "2021-01-01"),
        "valid": ("2021-01-01", "2021-07-01"),
        "test": ("2021-07-01", "2021-12-31"),
    }
    # 不重叠且有序 -> 通过
    assert_segments_disjoint(segs)


def test_segments_overlap_raises():
    segs = {
        "train": ("2020-01-01", "2021-02-01"),
        "valid": ("2021-01-01", "2021-07-01"),  # 与 train 重叠
        "test": ("2021-07-01", "2021-12-31"),
    }
    import pytest

    with pytest.raises(ValueError):
        assert_segments_disjoint(segs)
