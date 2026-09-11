"""Multi-security Provider queries must stay semantically identical while batching SQL."""

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal


pytestmark = pytest.mark.requires_dolt


def _count_queries(provider, monkeypatch):
    original = provider.connection.query
    calls = []

    def counted(sql, args=None):
        calls.append((sql, args))
        return original(sql, args)

    monkeypatch.setattr(provider.connection, "query", counted)
    return calls


@pytest.mark.unit
def test_multi_security_extras_matches_single_queries_in_two_sql_calls(live_provider, monkeypatch):
    stocks = ["600519.XSHG", "000001.XSHE", "600000.XSHG"]
    expected = {
        field: pd.concat(
            [live_provider.get_extras(field, stock, end_date="2023-08-31", count=1) for stock in stocks],
            axis=1,
        )
        for field in ("is_st", "tradestatus")
    }
    calls = _count_queries(live_provider, monkeypatch)
    actual = {
        field: live_provider.get_extras(field, stocks, end_date="2023-08-31", count=1)
        for field in ("is_st", "tradestatus")
    }
    assert len(calls) == 2
    for field in expected:
        assert_frame_equal(actual[field], expected[field])


@pytest.mark.unit
def test_multi_security_price_matches_single_queries_in_one_sql_call(live_provider, monkeypatch):
    stocks = ["600519.XSHG", "000001.XSHE", "600000.XSHG"]
    expected = live_provider.get_price(
        stocks, end_date="2023-08-31", count=20, fields=["close"], panel=True
    )
    calls = _count_queries(live_provider, monkeypatch)
    actual = live_provider.get_price(
        stocks, end_date="2023-08-31", count=20, fields=["close"], panel=True
    )
    assert len(calls) == 1
    assert_frame_equal(actual, expected)
