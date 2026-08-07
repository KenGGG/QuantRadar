"""QuantRadar 启动 bootstrap（见 docs/03 Bootstrap 契约）。

正式初始化顺序：
    启动 QuantRadar
    → import BulletTrade
    → register_data_provider("investment_data", factory)
    → set_data_provider("investment_data")
    → 验证 provider.name == "investment_data"
    → 才允许数据查询 / 回测

不依赖 DEFAULT_DATA_PROVIDER=investment_data 在 BulletTrade import 阶段自动注册
（BulletTrade 的 _provider = _create_provider() 在 import 阶段执行，彼时外部 Registry 为空）。
"""

from __future__ import annotations

from typing import Optional

from bullet_trade.data import (
    get_data_provider,
    register_data_provider,
    set_data_provider,
)

from .config import InvestmentDataConfig, load_investment_data_config
from .providers.investment_data.connection import InvestmentDataConnectionError
from .providers.investment_data.provider import InvestmentDataProvider

PROVIDER_NAME = "investment_data"


def investment_data_factory(_bullet_trade_config: Optional[dict] = None) -> InvestmentDataProvider:
    """Registry 工厂：忽略 BulletTrade 传入的配置 dict，改由 QuantRadar 自身配置构造。

    factory 契约为 factory(config: dict) -> DataProvider；本 Provider 的配置来源于
    QuantRadar 的 INVESTMENT_DATA_* 环境变量（见 config.load_investment_data_config）。
    """
    return InvestmentDataProvider(load_investment_data_config())


def bootstrap_investment_data(
    config: Optional[InvestmentDataConfig] = None,
    *,
    set_active: bool = True,
    overwrite: bool = True,
) -> InvestmentDataProvider:
    """注册并（可选）激活 InvestmentDataProvider。

    Args:
        config: 显式配置；为 None 时从环境变量加载。
        set_active: True 则调用 set_data_provider 将其设为全局 active provider 并校验。
        overwrite: True 允许重复注册（bootstrap 幂等）。

    Returns:
        已构造（或已激活）的 InvestmentDataProvider 实例。

    Raises:
        InvestmentDataConnectionError: 连接探针失败（仅当 set_active 时触发 auth 校验）。
        RuntimeError: 激活后 provider.name 校验不符。
    """
    if config is not None:
        # 允许显式传入配置：包一层工厂以固定该配置
        def _factory(_cfg=None):  # noqa: ANN001
            return InvestmentDataProvider(config)

        register_data_provider(PROVIDER_NAME, _factory, overwrite=overwrite)
    else:
        register_data_provider(PROVIDER_NAME, investment_data_factory, overwrite=overwrite)

    if set_active:
        set_data_provider(PROVIDER_NAME)
        provider = get_data_provider()
        if provider.name != PROVIDER_NAME:
            raise RuntimeError(
                f"bootstrap 校验失败：当前 provider.name={provider.name!r}，期望 {PROVIDER_NAME!r}"
            )
        return provider

    return investment_data_factory()
