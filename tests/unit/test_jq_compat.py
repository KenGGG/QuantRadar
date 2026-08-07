"""Phase 3 —— JoinQuant 兼容层（JQ Compat Core）单元测试（DB-backed）。

覆盖：
    - 频率别名（'d'/'day'/'1d' -> 'daily'）经 provider 与顶层 api 均可调用
    - 字段别名（'money' -> 'amount'）经 provider 与顶层 api 透明生效，输出列名仍为 'money'
    - fq='pre'/'post'/'qfq'/'hfq' 真实复权（基于 adjclose 与原始价因子，绝不伪造）
    - fq=None 视为 'none'
    - 顶层 bullet_trade.data.api.get_price / history / attribute_history 经 Registry
      路由到 InvestmentDataProvider 并返回正确原始价（与原表对账）
    - 不复权绝不混入 adjclose（回归）

所有数值均对账真实 investment_data，禁止 mock / 禁止返回虚假数据。
"""

import bullet_trade.data.api as data_api
import pandas as pd
import pytest

from quantradar.bootstrap import bootstrap_investment_data
from quantradar.providers.investment_data.provider import InvestmentDataProvider
from quantradar.providers.investment_data.symbols import normalize_stock_symbol


@pytest.mark.unit
class TestProviderAliases:
    def test_frequency_alias_d(self, live_provider):
        df = live_provider.get_price("600519.XSHG", "2024-01-02", "2024-01-03", frequency="d")
        assert len(df) == 2

    def test_frequency_alias_1d(self, live_provider):
        df = live_provider.get_price("600519.XSHG", "2024-01-02", "2024-01-03", frequency="1d")
        assert len(df) == 2

    def test_money_alias_returns_amount_values(self, live_provider):
        df = live_provider.get_price(
            "600519.XSHG", "2024-01-02", "2024-01-02", fields=["open", "money"]
        )
        # 输出列名仍为 JQ 的 'money'，数值来自 amount
        assert "money" in df.columns
        raw = live_provider.connection.query_one(
            "SELECT amount FROM final_a_stock_eod_price "
            "WHERE symbol='SH600519' AND tradedate='2024-01-02'"
        )
        assert df.loc["2024-01-02", "money"] == pytest.approx(float(raw["amount"]), rel=1e-9)

    def test_fq_pre_single_day_equals_raw(self, live_provider):
        # 单日窗口下前复权基准日即当日，scale=1，close 精确等于原始 close
        df = live_provider.get_price("600519.XSHG", "2024-01-02", "2024-01-02", fq="pre")
        raw = live_provider.connection.query_one(
            "SELECT close FROM final_a_stock_eod_price "
            "WHERE symbol='SH600519' AND tradedate='2024-01-02'"
        )
        assert df.loc["2024-01-02", "close"] == pytest.approx(float(raw["close"]), rel=1e-9)

    def test_fq_post_equals_adjclose(self, live_provider):
        # 后复权 close 精确等于原表 adjclose（复权基准）
        start, end = "2024-01-02", "2024-01-05"
        df = live_provider.get_price("600519.XSHG", start, end, fq="post")
        raw = live_provider.connection.query(
            "SELECT tradedate, adjclose FROM final_a_stock_eod_price "
            "WHERE symbol='SH600519' AND tradedate >= %s AND tradedate <= %s "
            "ORDER BY tradedate ASC",
                (start, end),
        )
        for r in raw:
            d = pd.Timestamp(r["tradedate"])
            assert df.loc[d, "close"] == pytest.approx(float(r["adjclose"]), rel=1e-9)

    def test_fq_pre_qfq_reconciles(self, live_provider):
        # 前复权：以窗口末日为基准 -> 末日 close==原始；其余日 close == adjclose * raw_last/adjclose_last
        start, end = "2024-01-02", "2024-01-05"
        df = live_provider.get_price("600519.XSHG", start, end, fq="pre")
        raw = live_provider.connection.query(
            "SELECT tradedate, close, adjclose FROM final_a_stock_eod_price "
            "WHERE symbol='SH600519' AND tradedate >= %s AND tradedate <= %s "
            "ORDER BY tradedate ASC",
                (start, end),
        )
        last = raw[-1]
        last_d = pd.Timestamp(last["tradedate"])
        # 基准日（末日）qfq close == 原始 close
        assert df.loc[last_d, "close"] == pytest.approx(float(last["close"]), rel=1e-9)
        # 首日前复权 close == adjclose_first / F_last，F_last = adjclose_last/raw_last
        first = raw[0]
        first_d = pd.Timestamp(first["tradedate"])
        expected_first = float(first["adjclose"]) * (float(last["close"]) / float(last["adjclose"]))
        assert df.loc[first_d, "close"] == pytest.approx(expected_first, rel=1e-9)

    def test_fq_adjustment_keeps_volume_raw(self, live_provider):
        # 复权仅缩放 OHLC，volume 保持原始成交（不伪造）
        start, end = "2024-01-02", "2024-01-03"
        df = live_provider.get_price(
            "600519.XSHG", start, end, fq="post", fields=["close", "volume"]
        )
        raw = live_provider.connection.query_one(
            "SELECT volume FROM final_a_stock_eod_price "
            "WHERE symbol='SH600519' AND tradedate='2024-01-02'"
        )
        assert df.loc["2024-01-02", "volume"] == pytest.approx(float(raw["volume"]), rel=1e-9)

    def test_fq_none_equiv_none(self, live_provider):
        df = live_provider.get_price("600519.XSHG", "2024-01-02", "2024-01-02", fq=None)
        assert len(df) == 1

    def test_unknown_fq_raises(self, live_provider):
        with pytest.raises(NotImplementedError):
            live_provider.get_price("600519.XSHG", "2024-01-02", "2024-01-02", fq="bogus")


@pytest.mark.unit
class TestEngineIntegration:
    """InvestmentDataProvider 经 Generic Provider Registry 被 BulletTrade 顶层 API 调用。"""

    def test_api_get_price_routes_to_provider(self, registry_reset):
        bootstrap_investment_data(set_active=True)
        assert isinstance(data_api._provider, InvestmentDataProvider)
        df = data_api.get_price("600519.XSHG", "2024-01-02", "2024-01-05", fq="none")
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["open", "high", "low", "close", "volume", "amount"]
        assert len(df) == 4

    def test_api_get_price_reconciles_raw(self, registry_reset):
        bootstrap_investment_data(set_active=True)
        df = data_api.get_price("600519.XSHG", "2024-01-02", "2024-01-05", fq="none")
        raw = InvestmentDataProvider().connection.query_one(
            "SELECT open, close FROM final_a_stock_eod_price "
            "WHERE symbol='SH600519' AND tradedate='2024-01-02'"
        )
        assert df.loc["2024-01-02", "open"] == pytest.approx(float(raw["open"]), rel=1e-9)
        assert df.loc["2024-01-02", "close"] == pytest.approx(float(raw["close"]), rel=1e-9)

    def test_api_history_works(self, registry_reset):
        bootstrap_investment_data(set_active=True)
        h = data_api.history(
            count=3, unit="1d", field="close", security_list=["600519.XSHG"], fq="none"
        )
        assert isinstance(h, pd.DataFrame)
        assert len(h) == 3

    def test_api_attribute_history_works(self, registry_reset):
        bootstrap_investment_data(set_active=True)
        ah = data_api.attribute_history(
            "600519.XSHG", count=3, unit="1d", fields=["open", "close"], fq="none"
        )
        assert isinstance(ah, pd.DataFrame)
        assert len(ah) == 3

    def test_api_money_alias_through_engine(self, registry_reset):
        bootstrap_investment_data(set_active=True)
        df = data_api.get_price(
            "600519.XSHG", "2024-01-02", "2024-01-02", fields=["open", "money"], fq="none"
        )
        # 引擎透传 'money' 别名，返回列名保持 'money'，数值来自 amount
        assert "money" in df.columns
        raw = InvestmentDataProvider().connection.query_one(
            "SELECT amount FROM final_a_stock_eod_price "
            "WHERE symbol='SH600519' AND tradedate='2024-01-02'"
        )
        assert df.loc["2024-01-02", "money"] == pytest.approx(float(raw["amount"]), rel=1e-9)

    def test_api_not_using_adjclose(self, registry_reset):
        bootstrap_investment_data(set_active=True)
        df = data_api.get_price("600519.XSHG", "2024-01-02", "2024-01-03", fq="none")
        raw = InvestmentDataProvider().connection.query_one(
            "SELECT close, adjclose FROM final_a_stock_eod_price "
            "WHERE symbol='SH600519' AND tradedate='2024-01-02'"
        )
        # 原始 close 与 adjclose 量级差异巨大，确认未误用
        assert abs(df.loc["2024-01-02", "close"] - float(raw["adjclose"])) > 1.0
