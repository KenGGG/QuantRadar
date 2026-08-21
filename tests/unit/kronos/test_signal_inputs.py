from __future__ import annotations

import datetime as dt

from quantradar.kronos.signal.inputs import list_signal_dates


class _Connection:
    def __init__(self):
        self.sql = None
        self.params = None

    def query(self, sql, params):
        self.sql = sql
        self.params = params
        return [
            {"trade_date": dt.date(2022, 6, 24)},
            {"trade_date": dt.date(2022, 7, 1)},
        ]


class _Provider:
    def __init__(self):
        self.connection = _Connection()


def test_list_signal_dates_uses_exact_pit_snapshots_in_requested_range():
    provider = _Provider()
    dates = list_signal_dates(provider, start="2022-06-01", end="2022-07-01")
    assert dates == [dt.date(2022, 6, 24), dt.date(2022, 7, 1)]
    assert "index_code = %s" in provider.connection.sql
    assert "trade_date BETWEEN %s AND %s" in provider.connection.sql
    assert provider.connection.params == ("000300.SH", "2022-06-01", "2022-07-01")
