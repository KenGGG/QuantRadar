import sys
from types import ModuleType

import pandas as pd
import pytest

import bullet_trade.data.api as data_api
from bullet_trade.data.providers.base import DataProvider


class DummyProvider(DataProvider):
    name = "dummy"

    def __init__(self, should_fail: bool = False):
        self.auth_calls = 0
        self.should_fail = should_fail

    def auth(self, user=None, pwd=None, host=None, port=None):
        self.auth_calls += 1
        if self.should_fail:
            raise RuntimeError("缺少凭证")

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
def test_get_data_provider_by_name_reuses_cache(monkeypatch):
    created = []

    def _fake_create(provider_name=None, overrides=None):
        created.append(provider_name)
        return DummyProvider()

    monkeypatch.setattr(data_api, "_create_provider", _fake_create)
    monkeypatch.setattr(data_api, "_provider_cache", {})
    monkeypatch.setattr(data_api, "_provider_auth_attempted", {})

    provider1 = data_api.get_data_provider("dummy")
    provider2 = data_api.get_data_provider("dummy")

    assert provider1 is provider2
    assert provider1.auth_calls == 1
    assert created == ["dummy"]


@pytest.mark.unit
def test_get_data_provider_auth_failure(monkeypatch):
    def _fake_create(provider_name=None, overrides=None):
        return DummyProvider(should_fail=True)

    monkeypatch.setattr(data_api, "_create_provider", _fake_create)
    monkeypatch.setattr(data_api, "_provider_cache", {})
    monkeypatch.setattr(data_api, "_provider_auth_attempted", {})

    with pytest.raises(RuntimeError, match="dummy 数据源认证失败"):
        data_api.get_data_provider("dummy")


@pytest.mark.unit
def test_sdk_fallback_to_module(monkeypatch):
    module = ModuleType("jqdatasdk")

    def special_method(value):
        return f"via-sdk-{value}"

    module.special_method = special_method  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "jqdatasdk", module)

    def _fake_create(provider_name=None, overrides=None):
        return DummyProvider()

    monkeypatch.setattr(data_api, "_create_provider", _fake_create)
    monkeypatch.setattr(data_api, "_provider_cache", {})
    monkeypatch.setattr(data_api, "_provider_auth_attempted", {})

    provider = data_api.get_data_provider("jqdata")
    assert provider.special_method("x") == "via-sdk-x"


@pytest.mark.unit
def test_remote_qmt_has_no_sdk_fallback(monkeypatch):
    class RemoteDummy(DummyProvider):
        name = "remote_qmt"

    def _fake_create(provider_name=None, overrides=None):
        return RemoteDummy()

    monkeypatch.setattr(data_api, "_create_provider", _fake_create)
    monkeypatch.setattr(data_api, "_provider_cache", {})
    monkeypatch.setattr(data_api, "_provider_auth_attempted", {})

    provider = data_api.get_data_provider("remote_qmt")
    with pytest.raises(AttributeError, match="无可用的 SDK 回退路径"):
        _ = provider.some_missing_method()
