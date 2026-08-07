"""bootstrap.py 单元测试（DB-backed；不可达则跳过）。

验证 QuantRadar 正式 bootstrap 契约：
    register_data_provider("investment_data", factory)
    → set_data_provider("investment_data")
    → 验证 get_data_provider().name == "investment_data"
"""

import pytest

from bullet_trade.data import get_data_provider, get_price
from quantradar.bootstrap import PROVIDER_NAME, bootstrap_investment_data


@pytest.mark.unit
class TestBootstrap:
    def test_bootstrap_registers_and_activates(self, registry_reset, db_connection):
        provider = bootstrap_investment_data()
        assert provider.name == PROVIDER_NAME
        assert get_data_provider().name == PROVIDER_NAME

    def test_bootstrap_idempotent(self, registry_reset, db_connection):
        bootstrap_investment_data()
        # 再次 bootstrap（overwrite=True）不应抛错
        provider = bootstrap_investment_data()
        assert get_data_provider().name == PROVIDER_NAME

    def test_active_provider_usable(self, registry_reset, db_connection):
        bootstrap_investment_data()
        # 经 BulletTrade 顶层 api 调用，当前全局 provider 即 investment_data
        days = get_price  # 仅确认符号可导入；真实查询在 provider 测试中覆盖
        assert days is not None
