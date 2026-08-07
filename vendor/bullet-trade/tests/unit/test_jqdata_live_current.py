from types import SimpleNamespace
from datetime import datetime, date

import pandas as pd

from bullet_trade.data.providers.jqdata import JQDataProvider


class FakeJQ:
    def __init__(self):
        # Defaults; tests will override per scenario
        self._tick = None
        self._secinfo = None
        self._minute_df = None
        self._daily_df = None
        self._extras = {}

    def get_current_tick(self, security):
        return self._tick

    def get_security_info(self, security):
        return self._secinfo

    def get_price(self, security, count, end_date, frequency, fields):
        if frequency == 'minute':
            return self._minute_df
        if frequency == 'daily':
            return self._daily_df
        return pd.DataFrame()

    def get_extras(self, name, securities, start_date, end_date):
        # Return a DataFrame with a single row for the requested field
        val = self._extras.get(name)
        if val is None:
            return pd.DataFrame()
        # For simplicity, return a 1x1 frame
        return pd.DataFrame({securities[0]: [val]}).T


def test_jq_live_current_from_tick(monkeypatch):
    provider = JQDataProvider({})
    fake = FakeJQ()
    fake._tick = {'last_price': 12.34}
    fake._secinfo = SimpleNamespace(high_limit=13.5, low_limit=11.0)
    fake._extras['is_paused'] = 0

    # Patch module-level jq symbol used by provider
    monkeypatch.setattr('bullet_trade.data.providers.jqdata.jq', fake, raising=False)

    snap = provider.get_live_current('000001.XSHE')
    assert snap['last_price'] == 12.34
    assert snap['high_limit'] == 13.5
    assert snap['low_limit'] == 11.0
    assert snap['paused'] is False


def test_jq_live_current_from_minute_price(monkeypatch):
    provider = JQDataProvider({})
    fake = FakeJQ()
    # No tick; use minute price
    fake._minute_df = pd.DataFrame([
        {'close': 10.2, 'high_limit': 11.22, 'low_limit': 9.18}
    ], index=[pd.to_datetime(datetime.now())])

    monkeypatch.setattr('bullet_trade.data.providers.jqdata.jq', fake, raising=False)
    snap = provider.get_live_current('000001.XSHE')
    assert snap['last_price'] == 10.2
    assert snap['high_limit'] == 11.22
    assert snap['low_limit'] == 9.18


def test_jq_live_current_infer_limits_from_preclose_and_st(monkeypatch):
    provider = JQDataProvider({})
    fake = FakeJQ()
    # No tick and minute df lacks limits; daily to infer pre_close
    # Build daily with two rows; use last two closes: prev=20.0
    fake._daily_df = pd.DataFrame([
        {'close': 19.5},
        {'close': 20.0},
    ], index=[pd.to_datetime(date(2025, 1, 1)), pd.to_datetime(date(2025, 1, 2))])
    # Mark ST (5% limit)
    fake._extras['is_st'] = 1

    # Minute DF without limit fields
    fake._minute_df = pd.DataFrame([
        {'close': 20.1}
    ], index=[pd.to_datetime(datetime.now())])

    monkeypatch.setattr('bullet_trade.data.providers.jqdata.jq', fake, raising=False)
    snap = provider.get_live_current('000001.XSHE')
    assert abs(snap['high_limit'] - 21.0) < 1e-6  # 20 * 1.05
    assert abs(snap['low_limit'] - 19.0) < 1e-6   # 20 * 0.95
    assert snap['last_price'] == 20.1
