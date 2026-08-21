from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from quantradar.kronos.data_audit.actions import detect_action_candidates
from quantradar.kronos.data_audit.prices import (
    expected_adjusted_prices,
    select_board_pool,
    select_diverse_symbols,
)
from quantradar.kronos.data_audit.schema import unique_index_covers
from quantradar.kronos.data_audit.universe import (
    last_trading_day_per_week,
    select_auditable_weeks,
    select_evenly,
)


def test_expected_adjusted_prices_uses_explicit_qfq_reference_and_keeps_volume_amount():
    raw = pd.DataFrame(
        {
            "open": [10.0, 5.0],
            "high": [11.0, 6.0],
            "low": [9.0, 4.0],
            "close": [10.0, 5.0],
            "adjclose": [10.0, 10.0],
            "volume": [100.0, 200.0],
            "amount": [1_000.0, 1_100.0],
        },
        index=pd.to_datetime(["2023-01-02", "2023-01-03"]),
    )

    hfq = expected_adjusted_prices(raw, "hfq")
    qfq = expected_adjusted_prices(raw, "qfq", reference_date=dt.date(2023, 1, 3))

    assert hfq["close"].tolist() == [10.0, 10.0]
    assert qfq["close"].tolist() == [5.0, 5.0]
    assert qfq["volume"].tolist() == [100.0, 200.0]
    assert qfq["amount"].tolist() == [1_000.0, 1_100.0]


def test_expected_adjusted_prices_rejects_missing_or_invalid_factor():
    raw = pd.DataFrame(
        {"open": [1.0], "high": [1.0], "low": [1.0], "close": [0.0], "adjclose": [1.0]},
        index=pd.to_datetime(["2023-01-02"]),
    )

    with pytest.raises(ValueError, match="positive close"):
        expected_adjusted_prices(raw, "hfq")


def test_select_diverse_symbols_round_robins_boards_and_price_buckets():
    candidates = [
        {"symbol": "SH600001", "avg_close": 5.0},
        {"symbol": "SH600002", "avg_close": 50.0},
        {"symbol": "SH688001", "avg_close": 150.0},
        {"symbol": "SZ000001", "avg_close": 8.0},
        {"symbol": "SZ000002", "avg_close": 80.0},
        {"symbol": "SZ300001", "avg_close": 30.0},
    ]

    selected = select_diverse_symbols(candidates, limit=6)

    assert selected == [
        "SH600001",
        "SH600002",
        "SH688001",
        "SZ000001",
        "SZ000002",
        "SZ300001",
    ]


def test_select_board_pool_caps_each_board_without_losing_small_boards():
    symbols = [
        "SH600001",
        "SH600002",
        "SH600003",
        "SH688001",
        "SZ000001",
        "SZ300001",
    ]

    assert select_board_pool(symbols, per_board=2) == [
        "SH600001",
        "SH600002",
        "SH688001",
        "SZ000001",
        "SZ300001",
    ]


def test_detect_action_candidates_reports_factor_and_preclose_evidence_without_claiming_type():
    rows = [
        {
            "symbol": "SH600519",
            "tradedate": dt.date(2022, 6, 29),
            "close": 2030.0,
            "preclose": 2036.0,
            "adjfactor": 6.628762,
        },
        {
            "symbol": "SH600519",
            "tradedate": dt.date(2022, 6, 30),
            "close": 2045.0,
            "preclose": 2008.33,
            "adjfactor": 6.700286,
        },
    ]

    events = detect_action_candidates(rows)

    assert len(events) == 1
    assert events[0]["ex_date"] == dt.date(2022, 6, 30)
    assert events[0]["preclose_gap_proxy"] == pytest.approx(21.67)
    assert events[0]["factor_ratio"] == pytest.approx(6.700286 / 6.628762)
    assert events[0]["authoritative_event_type"] is False
    assert events[0]["accounting_verified"] is False


def test_week_helpers_choose_last_open_day_and_evenly_spaced_dates():
    days = [
        dt.date(2023, 1, 2),
        dt.date(2023, 1, 6),
        dt.date(2023, 1, 9),
        dt.date(2023, 1, 13),
        dt.date(2023, 1, 16),
        dt.date(2023, 1, 20),
        dt.date(2023, 1, 23),
    ]

    weekly = last_trading_day_per_week(days)

    assert weekly == [
        dt.date(2023, 1, 6),
        dt.date(2023, 1, 13),
        dt.date(2023, 1, 20),
        dt.date(2023, 1, 23),
    ]
    assert select_evenly(weekly, 3) == [
        dt.date(2023, 1, 6),
        dt.date(2023, 1, 13),
        dt.date(2023, 1, 23),
    ]


def test_unique_index_covers_accepts_same_columns_regardless_of_primary_key_order():
    indexes = [
        {"Non_unique": 0, "Key_name": "PRIMARY", "Seq_in_index": 1, "Column_name": "tradedate"},
        {"Non_unique": 0, "Key_name": "PRIMARY", "Seq_in_index": 2, "Column_name": "symbol"},
        {"Non_unique": 1, "Key_name": "symbol", "Seq_in_index": 1, "Column_name": "symbol"},
    ]

    assert unique_index_covers(indexes, ("symbol", "tradedate")) is True
    assert unique_index_covers(indexes, ("symbol",)) is False


def test_select_auditable_weeks_excludes_dates_outside_index_snapshot_coverage():
    days = [dt.date(2019, 12, 27), dt.date(2020, 1, 3), dt.date(2020, 1, 10)]

    assert select_auditable_weeks(
        days,
        first_snapshot=dt.date(2020, 1, 2),
        last_snapshot=dt.date(2020, 1, 9),
        count=5,
    ) == [dt.date(2020, 1, 3)]
