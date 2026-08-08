"""QuantRadar 单元测试公共 fixture。

- db_connection：尝试连接 investment_data；不可达则跳过（保证套件在新机器上不因缺 DB 而崩）。
- live_provider：返回已构造的 InvestmentDataProvider（只读，不发起查询直到调用方法）。
- registry_reset：保存/恢复 BulletTrade 的 Generic Provider Registry 与全局 active provider，
  避免 bootstrap 测试污染其它测试。
"""

from __future__ import annotations

import os
from typing import Optional

import pytest

import bullet_trade.data.api as data_api
from quantradar.config import load_investment_data_config
from quantradar.providers.investment_data.connection import (
    InvestmentDataConnection,
    InvestmentDataConnectionError,
)
from quantradar.providers.investment_data.provider import InvestmentDataProvider

# Dolt 可达性缓存（整个测试会话只探测一次，CI 无 Dolt 时全体 requires_dolt 测试 skip）。
_DOLT_REACHABLE: Optional[bool] = None


def dolt_reachable() -> bool:
    """investment_data（Dolt）是否可达。QUANTRADAR_FORCE_NO_DOLT=1 强制视为不可达（用于本地模拟 CI）。"""
    global _DOLT_REACHABLE
    if os.environ.get("QUANTRADAR_FORCE_NO_DOLT") == "1":
        return False
    if _DOLT_REACHABLE is None:
        try:
            conn = InvestmentDataConnection(load_investment_data_config())
            conn.check()
            conn.close()
            _DOLT_REACHABLE = True
        except Exception:
            _DOLT_REACHABLE = False
    return _DOLT_REACHABLE


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "requires_dolt: 需要可达的 investment_data(Dolt)；不可达时自动 skip"
    )


@pytest.fixture(autouse=True)
def _skip_without_dolt(request):
    """标记了 requires_dolt 的测试，在 Dolt 不可达时自动 skip（保证 CI 无 Dolt 仍绿）。"""
    if request.node.get_closest_marker("requires_dolt") and not dolt_reachable():
        pytest.skip("investment_data(Dolt) 不可达：跳过需要 Dolt 的测试")
    yield


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


@pytest.fixture(autouse=True)
def _clear_current_context():
    """回测会写入 BulletTrade 全局 _current_context；每个测试后清空，避免跨测试污染。

    仅限测试基础设施，不改 BulletTrade 核心。
    """
    yield
    try:
        data_api.set_current_context(None)
    except Exception:
        pass
