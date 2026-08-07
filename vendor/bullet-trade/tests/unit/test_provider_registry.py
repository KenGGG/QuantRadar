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


# ---------------------------------------------------------------------------
# Phase 1.1：Provider Registry 生命周期加固
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_unregister_clears_registry_cache_and_auth(registry_cleanup):
    """T10：unregister 必须清除 Registry / instance cache / auth state（显式断言）。"""
    register_data_provider("dummy", lambda cfg: RegistryDummyProvider())
    p = get_data_provider("dummy")  # 触发缓存 + 认证态写入

    # 注册并获取后，三个结构都应包含 dummy
    assert "dummy" in data_api._PROVIDER_REGISTRY
    assert "dummy" in data_api._provider_cache
    assert "dummy" in data_api._provider_auth_attempted

    unregister_data_provider("dummy")

    # unregister 后，三者都必须移除 dummy
    assert "dummy" not in data_api._PROVIDER_REGISTRY
    assert "dummy" not in data_api._provider_cache
    assert "dummy" not in data_api._provider_auth_attempted


@pytest.mark.unit
def test_overwrite_clears_cache_and_uses_new_factory(registry_cleanup):
    """T11：overwrite=True 后，按名获取必须用新 factory 创建新实例。"""
    created = []

    def factory_v1(cfg):
        p = RegistryDummyProvider()
        created.append(("v1", p))
        return p

    def factory_v2(cfg):
        p = RegistryDummyProvider()
        created.append(("v2", p))
        return p

    register_data_provider("dummy", factory_v1)
    p1 = get_data_provider("dummy")
    assert created[-1][0] == "v1"
    assert p1 is created[-1][1]

    register_data_provider("dummy", factory_v2, overwrite=True)
    p2 = get_data_provider("dummy")
    assert created[-1][0] == "v2"
    assert p2 is created[-1][1]
    # 旧缓存被清除，必须使用新 factory 的新实例
    assert p2 is not p1


@pytest.mark.unit
def test_unregister_cached_provider_then_get_by_name_fails(registry_cleanup):
    """T12：注销当前已缓存 Provider 后，按名重新获取必须明确失败。"""
    register_data_provider("dummy", lambda cfg: RegistryDummyProvider())
    p = get_data_provider("dummy")
    assert "dummy" in data_api._PROVIDER_REGISTRY and "dummy" in data_api._provider_cache

    unregister_data_provider("dummy")
    with pytest.raises(ValueError):
        get_data_provider("dummy")


@pytest.mark.unit
def test_unregister_does_not_switch_active_global_provider(registry_cleanup):
    """T13：unregister 当前全局 Provider 时，不偷偷切换已激活的全局 _provider。"""
    register_data_provider("dummy", lambda cfg: RegistryDummyProvider())
    set_data_provider("dummy")  # 把 dummy 设为全局 active provider
    assert isinstance(get_data_provider(), RegistryDummyProvider)

    # unregister 只清 Registry/cache/auth，不改变全局 _provider
    unregister_data_provider("dummy")
    assert isinstance(get_data_provider(), RegistryDummyProvider)  # 全局仍为 dummy
    # 但按名获取已因 Registry 缺失而失败（与全局是两个层面）
    with pytest.raises(ValueError):
        get_data_provider("dummy")
