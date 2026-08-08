"""InvestmentDataProvider 单元测试（DB-backed；investment_data 不可达时跳过）。

覆盖 Phase 2A：
    - auth / 连接校验
    - get_trade_days（区间 / count from end / count from start）
    - get_all_securities（列结构 / 非 stock 类型 / Point-in-Time 上市前剔除）
    - get_security_info（存在 / 缺 name）
    - get_index_stocks（成分数量 / JoinQuant 代码 / PIT 指数成立前为空）
    - get_index_weights（数量 / 浮点 / PIT）
    - get_price / get_split_dividend 明确 NotImplementedError（禁止虚假数据）
"""

import pytest

pytestmark = pytest.mark.requires_dolt

from quantradar.providers.investment_data.provider import InvestmentDataProvider


@pytest.mark.unit
class TestAuth:
    def test_auth_ok(self, live_provider):
        # 不抛异常即通过连接探针
        live_provider.auth()


@pytest.mark.unit
class TestTradeDays:
    def test_range(self, live_provider):
        days = live_provider.get_trade_days("2024-01-01", "2024-01-10")
        strs = [d.strftime("%Y-%m-%d") for d in days]
        # 2024-01-01 元旦休市，首个交易日为 01-02
        assert strs == [
            "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05",
            "2024-01-08", "2024-01-09", "2024-01-10",
        ]

    def test_count_from_end(self, live_provider):
        days = live_provider.get_trade_days(end_date="2024-01-10", count=5)
        assert [d.strftime("%Y-%m-%d") for d in days] == [
            "2024-01-04", "2024-01-05", "2024-01-08", "2024-01-09", "2024-01-10",
        ]

    def test_count_from_start(self, live_provider):
        days = live_provider.get_trade_days(start_date="2024-01-02", count=3)
        assert [d.strftime("%Y-%m-%d") for d in days] == [
            "2024-01-02", "2024-01-03", "2024-01-04",
        ]

    def test_return_type_datetime(self, live_provider):
        days = live_provider.get_trade_days("2024-01-02", "2024-01-02")
        assert len(days) == 1
        assert isinstance(days[0], __import__("datetime").datetime)


@pytest.mark.unit
class TestAllSecurities:
    def test_columns_and_pit(self, live_provider):
        df = live_provider.get_all_securities(date="2020-06-01")
        assert list(df.columns) == ["display_name", "name", "start_date", "end_date", "type"]
        # 茅台 2001-08-27 上市，2020 应在列表；上市前 2000-01-01 不应在列表
        assert "600519.XSHG" in df.index
        before = live_provider.get_all_securities(date="2000-01-01")
        assert "600519.XSHG" not in before.index

    def test_non_stock_returns_empty_structure(self, live_provider):
        df = live_provider.get_all_securities(types="etf")
        assert list(df.columns) == ["display_name", "name", "start_date", "end_date", "type"]
        assert len(df) == 0

    def test_display_name_unavailable(self, live_provider):
        df = live_provider.get_all_securities(date="2020-06-01")
        # ts_a_stock_list 无 name 列 -> 明确为 NaN（PARTIAL/LIMIT，不伪造）
        assert df["display_name"].isna().all()
        assert df["name"].isna().all()


@pytest.mark.unit
class TestSecurityInfo:
    def test_exists(self, live_provider):
        info = live_provider.get_security_info("600519.XSHG")
        assert info["type"] == "stock"
        assert info["start_date"].strftime("%Y-%m-%d") == "2001-08-27"
        assert info["name"] is None  # 源无 name 列


@pytest.mark.unit
class TestIndex:
    def test_stocks_pit_and_count(self, live_provider):
        stocks = live_provider.get_index_stocks("000300.XSHG", "2024-01-02")
        assert len(stocks) == 300
        assert all(s.endswith((".XSHG", ".XSHE")) for s in stocks)
        assert "600519.XSHG" in stocks

    def test_stocks_before_launch_empty(self, live_provider):
        # 沪深300 2005-04-08 发布；此前无快照 -> 明确空列表（PIT，不回填）
        stocks = live_provider.get_index_stocks("000300.XSHG", "2000-01-01")
        assert stocks == []

    def test_weights_pit(self, live_provider):
        weights = live_provider.get_index_weights("000300.XSHG", "2024-01-02")
        assert len(weights) == 300
        assert all(isinstance(v, float) for v in weights.values())
        # 权重为百分比，合计约 100
        assert 99.0 < sum(weights.values()) < 101.0


@pytest.mark.unit
class TestCorporateActionImplemented:
    def test_get_split_dividend_requires_boundary(self, live_provider):
        # 已实现：无边界时明确抛 ValueError（避免全表扫描），不再 NotImplementedError
        with pytest.raises(ValueError):
            live_provider.get_split_dividend("600519.XSHG")
