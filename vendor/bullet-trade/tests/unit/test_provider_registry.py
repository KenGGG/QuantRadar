"""
Generic Provider Registry 单元测试（Phase 1）。

验证：
- register_data_provider / unregister_data_provider
- set_data_provider / get_data_provider / reload_data_provider_from_env 可通过名称创建外部 Provider
- 未知 Provider 明确 ValueError（不返回 stub）
- 重复注册默认拒绝（overwrite=True 可覆盖）
- 内置 Provider 创建逻辑不被破坏，且内置名称受保护

不实现真实 InvestmentDataProvider；仅用测试用 RegistryDummyProvider。
"""

import pandas as pd
import pytest

import bullet_trade.data.api as data_api
from bullet_trade.data import (
    register_data_provider,
    unregister_data_provider,
    set_data_provider,
    get_data_provider,
    reload_data_provider_from_env,
)
from bullet_trade.data.providers.base import DataProvider


class RegistryDummyProvider(DataProvider):
    name = "dummy"

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


@pytest.fixture
def registry_cleanup():
    """保存全局 provider 状态，测试后恢复并清空外部注册表，避免污染其它测试。"""
    saved_provider = data_api._provider
    saved_cache = dict(data_api._provider_cache)
    yield
    data_api._provider = saved_provider
    data_api._provider_cache.clear()
    data_api._provider_cache.update(saved_cache)
    for name in list(data_api._PROVIDER_REGISTRY.keys()):
        unregister_data_provider(name)


@pytest.mark.unit
def test_register_custom_provider(registry_cleanup):
    assert "dummy" not in data_api._PROVIDER_REGISTRY
    register_data_provider("dummy", lambda cfg: RegistryDummyProvider())
    assert "dummy" in data_api._PROVIDER_REGISTRY


@pytest.mark.unit
def test_set_data_provider_by_name(registry_cleanup):
    register_data_provider("dummy", lambda cfg: RegistryDummyProvider())
    set_data_provider("dummy")
    assert isinstance(get_data_provider(), RegistryDummyProvider)


@pytest.mark.unit
def test_get_data_provider_by_name_caches(registry_cleanup):
    register_data_provider("dummy", lambda cfg: RegistryDummyProvider())
    p = get_data_provider("dummy")
    assert isinstance(p, RegistryDummyProvider)
    # 应走缓存，返回同一实例
    assert get_data_provider("dummy") is p


@pytest.mark.unit
def test_reload_by_name(registry_cleanup):
    register_data_provider("dummy", lambda cfg: RegistryDummyProvider())
    reload_data_provider_from_env("dummy")
    assert isinstance(get_data_provider("dummy"), RegistryDummyProvider)


@pytest.mark.unit
def test_unknown_provider_raises_value_error(registry_cleanup):
    with pytest.raises(ValueError):
        get_data_provider("does_not_exist")


@pytest.mark.unit
def test_duplicate_register_refused_unless_overwrite(registry_cleanup):
    register_data_provider("dummy", lambda cfg: RegistryDummyProvider())
    with pytest.raises(ValueError):
        register_data_provider("dummy", lambda cfg: RegistryDummyProvider())
    # overwrite=True 允许覆盖
    register_data_provider("dummy", lambda cfg: RegistryDummyProvider(), overwrite=True)
    assert "dummy" in data_api._PROVIDER_REGISTRY


@pytest.mark.unit
def test_factory_receives_merged_config(registry_cleanup):
    captured = {}

    def factory(cfg):
        captured["cfg"] = cfg
        return RegistryDummyProvider()

    register_data_provider("dummy", factory)
    set_data_provider("dummy", my_override="v")
    assert isinstance(captured["cfg"], dict)
    assert captured["cfg"].get("my_override") == "v"


@pytest.mark.unit
def test_builtin_provider_still_creatable(registry_cleanup):
    from bullet_trade.data.providers.tushare import TushareProvider

    assert isinstance(data_api._create_provider("tushare"), TushareProvider)


@pytest.mark.unit
def test_builtin_name_protected(registry_cleanup):
    with pytest.raises(ValueError):
        register_data_provider("jqdata", lambda cfg: RegistryDummyProvider())
