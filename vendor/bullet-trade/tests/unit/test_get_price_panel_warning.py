import warnings

import pandas as pd
import pytest

import bullet_trade.data.api as data_api
from bullet_trade.data.providers.base import DataProvider


class DummyProvider(DataProvider):
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
def test_get_price_panel_warning_only_for_multi_security(monkeypatch):
    provider = DummyProvider()
    monkeypatch.setattr(data_api, "_provider", provider, raising=False)
    monkeypatch.setattr(data_api, "_auth_attempted", True, raising=False)
    monkeypatch.setattr(data_api, "_current_context", None, raising=False)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        data_api.get_price("000001.XSHE", start_date="2025-07-01", end_date="2025-07-01", panel=True)
    assert not caught

    with pytest.warns(UserWarning):
        data_api.get_price([
            "000001.XSHE",
            "000002.XSHE",
        ], start_date="2025-07-01", end_date="2025-07-01", panel=True)
