import pandas as pd
import pytest

import bullet_trade.data.api as data_api
from bullet_trade.data.providers.base import DataProvider


class DummyProvider(DataProvider):
    def __init__(self):
        self.auth_calls = 0

    def auth(self, user=None, pwd=None, host=None, port=None):
        self.auth_calls += 1

    def get_price(self, *args, **kwargs):
        return pd.DataFrame()

    def get_trade_days(self, *args, **kwargs):
        return []

    def get_all_securities(self, *args, **kwargs):
        return pd.DataFrame()

    def get_index_stocks(self, *args, **kwargs):
        return []

    def get_split_dividend(self, *args, **kwargs):
        return []


@pytest.mark.unit
def test_get_data_provider_triggers_auth_once(monkeypatch):
    dummy = DummyProvider()
    monkeypatch.setattr(data_api, '_provider', dummy, raising=False)
    monkeypatch.setattr(data_api, '_auth_attempted', False, raising=False)

    returned = data_api.get_data_provider()
    assert returned is dummy
    assert dummy.auth_calls == 1

    # Subsequent调用不会重复认证
    data_api.get_data_provider()
    assert dummy.auth_calls == 1
