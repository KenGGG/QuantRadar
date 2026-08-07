"""QuantRadar 单元测试公共 fixture。

- db_connection：尝试连接 investment_data；不可达则跳过（保证套件在新机器上不因缺 DB 而崩）。
- live_provider：返回已构造的 InvestmentDataProvider（只读，不发起查询直到调用方法）。
- registry_reset：保存/恢复 BulletTrade 的 Generic Provider Registry 与全局 active provider，
  避免 bootstrap 测试污染其它测试。
"""

from __future__ import annotations

import pytest

import bullet_trade.data.api as data_api
from quantradar.config import load_investment_data_config
from quantradar.providers.investment_data.connection import (
    InvestmentDataConnection,
    InvestmentDataConnectionError,
)
from quantradar.providers.investment_data.provider import InvestmentDataProvider


@pytest.fixture
def db_connection():
    """可达则提供只读连接，不可达则跳过。"""
    config = load_investment_data_config()
    conn = InvestmentDataConnection(config)
    try:
        conn.check()
    except InvestmentDataConnectionError as exc:
        pytest.skip(f"investment_data 不可达，跳过 DB 测试：{exc}")
    yield conn
    conn.close()


@pytest.fixture
def live_provider():
    """构造 InvestmentDataProvider（构造不连接，方法调用时才查询）。"""
    return InvestmentDataProvider(load_investment_data_config())


@pytest.fixture
def registry_reset():
    """保存并恢复 BulletTrade Registry / 全局 provider，测试后复位。"""
    saved_provider = data_api._provider
    saved_cache = dict(data_api._provider_cache)
    saved_registry = dict(data_api._PROVIDER_REGISTRY)
    saved_auth = dict(data_api._provider_auth_attempted)
    yield
    data_api._provider = saved_provider
    data_api._provider_cache.clear()
    data_api._provider_cache.update(saved_cache)
    data_api._PROVIDER_REGISTRY.clear()
    data_api._PROVIDER_REGISTRY.update(saved_registry)
    data_api._provider_auth_attempted.clear()
    data_api._provider_auth_attempted.update(saved_auth)
