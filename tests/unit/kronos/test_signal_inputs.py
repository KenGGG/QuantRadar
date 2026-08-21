from __future__ import annotations

import datetime as dt

from quantradar.kronos.signal.inputs import list_signal_dates
from quantradar.kronos.universe_spec import Universe


class _CalendarConnection:
    def __init__(self):
        self.queries: list[tuple[str, tuple]] = []

    def query(self, sql: str, params) -> list[dict]:
        self.queries.append((sql, params))
        return [
            {"date": dt.date(2022, 6, 20)},
            {"date": dt.date(2022, 6, 21)},
            {"date": dt.date(2022, 6, 24)},
            {"date": dt.date(2022, 6, 27)},
            {"date": dt.date(2022, 6, 28)},
        ]


class _IndexConnection:
    def __init__(self):
        self.sql = None
        self.params = None

    def query(self, sql: str, params) -> list[dict]:
        self.sql = sql
        self.params = params
        return [
            {"trade_date": dt.date(2022, 6, 24)},
            {"trade_date": dt.date(2022, 7, 1)},
        ]


class _Provider:
    def __init__(self, connection):
        self.connection = connection


def test_list_signal_dates_all_a_liquid_uses_calendar_not_index_pit():
    provider = _Provider(_CalendarConnection())
    dates = list_signal_dates(provider, start="2022-06-01", end="2022-07-01")
    # 每周最后一个交易日：06-24（第 25 周）、06-28（第 26 周）。
    assert dates == [dt.date(2022, 6, 24), dt.date(2022, 6, 28)]
    sql, params = provider.connection.queries[-1]
    assert "ts_trade_day_calendar" in sql
    assert "is_open" in sql
    assert params == ("2022-06-01", "2022-07-01")
    assert all("ts_index_weight" not in q for q, _ in provider.connection.queries)


def test_list_signal_dates_csi300_pit_uses_exact_pit_snapshots():
    provider = _Provider(_IndexConnection())
    dates = list_signal_dates(
        provider, start="2022-06-01", end="2022-07-01", universe=Universe.CSI300_PIT
    )
    assert dates == [dt.date(2022, 6, 24), dt.date(2022, 7, 1)]
    assert "index_code = %s" in provider.connection.sql
    assert "trade_date BETWEEN %s AND %s" in provider.connection.sql
    assert provider.connection.params == ("000300.SH", "2022-06-01", "2022-07-01")
