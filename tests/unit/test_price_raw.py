"""InvestmentDataProvider.get_price 单元测试（Phase 2B，DB-backed）。

覆盖：
    - 单证券普通窗口（600519.XSHG / 000001.XSHE）
    - 较早历史窗口（茅台 2001 上市初年）
    - count 取最近 N 日 / count + start 取前 N 日
    - fields 选择子集 / 非法字段抛错
    - 多证券 panel（MultiIndex(字段, 证券)）
    - 无数据窗口 / 上市前 / 退市后 -> 显式空（不伪造）
    - 与原表 final_a_stock_eod_price 抽样对账（数值一致，且不使用 adjclose）
    - frequency != 'daily' -> NotImplementedError；fq != 'none' -> NotImplementedError
    - 无边界（start/end/count 全 None）-> ValueError

数据正确性优先：所有对账直接比对原表，禁止用「接近」掩盖差异。
"""

import datetime

import pandas as pd
import pytest

pytestmark = pytest.mark.requires_dolt

from quantradar.providers.investment_data.provider import InvestmentDataProvider
from quantradar.providers.investment_data.symbols import normalize_stock_symbol

_PRICE_FIELDS = ["open", "high", "low", "close", "volume", "amount"]


@pytest.mark.unit
class TestGetPriceSingle:
    def test_window_shape_and_columns(self, live_provider):
        df = live_provider.get_price("600519.XSHG", "2024-01-02", "2024-01-05")
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == _PRICE_FIELDS
        assert len(df) == 4
        # 索引为日期
        assert isinstance(df.index, pd.DatetimeIndex)
        assert df.index.is_monotonic_increasing
        # 数值类型
        assert df.dtypes.map(lambda t: t == float).all()

    def test_early_history_window(self, live_provider):
        # 茅台 2001-08-27 上市；取上市初年一小段
        df = live_provider.get_price("600519.XSHG", "2001-09-01", "2001-09-10")
        assert len(df) >= 1
        assert df.index[0] >= pd.Timestamp("2001-09-01")
        # 上市前无数据，不应出现 2001-08-27 之前
        assert df.index.min() >= pd.Timestamp("2001-08-27")

    def test_other_security_window(self, live_provider):
        df = live_provider.get_price("000001.XSHE", "2024-01-02", "2024-01-05")
        assert list(df.columns) == _PRICE_FIELDS
        assert len(df) == 4

    def test_count_last_n(self, live_provider):
        df = live_provider.get_price("600519.XSHG", end_date="2024-01-05", count=3)
        assert len(df) == 3
        assert [d.strftime("%Y-%m-%d") for d in df.index] == [
            "2024-01-03", "2024-01-04", "2024-01-05",
        ]

    def test_count_from_start(self, live_provider):
        df = live_provider.get_price("600519.XSHG", start_date="2024-01-02", count=2)
        assert len(df) == 2
        assert [d.strftime("%Y-%m-%d") for d in df.index] == [
            "2024-01-02", "2024-01-03",
        ]

    def test_fields_subset(self, live_provider):
        df = live_provider.get_price(
            "600519.XSHG", "2024-01-02", "2024-01-03", fields=["open", "close"]
        )
        assert list(df.columns) == ["open", "close"]

    def test_invalid_field_raises(self, live_provider):
        with pytest.raises(ValueError):
            live_provider.get_price(
                "600519.XSHG", "2024-01-02", "2024-01-03", fields=["bogus"]
            )

    def test_no_boundary_raises(self, live_provider):
        with pytest.raises(ValueError):
            live_provider.get_price("600519.XSHG")

    def test_frequency_not_daily_raises(self, live_provider):
        with pytest.raises(NotImplementedError):
            live_provider.get_price(
                "600519.XSHG", "2024-01-02", "2024-01-03", frequency="minute"
            )

    def test_fq_pre_returns_raw_limit(self, live_provider):
        # fq='pre'/'post' 当前等价原始价（复权 LIMIT，Phase 5 补齐），不抛异常
        df = live_provider.get_price("600519.XSHG", "2024-01-02", "2024-01-03", fq="pre")
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2

    def test_unknown_fq_raises(self, live_provider):
        with pytest.raises(NotImplementedError):
            live_provider.get_price(
                "600519.XSHG", "2024-01-02", "2024-01-03", fq="bogus"
            )


@pytest.mark.unit
class TestGetPriceEmpty:
    def test_window_before_listing_empty(self, live_provider):
        df = live_provider.get_price("600519.XSHG", "1990-01-01", "1991-01-01")
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
        assert list(df.columns) == _PRICE_FIELDS

    def test_window_after_delisting_empty(self, live_provider):
        # 用一只已知长期退市的股票测试：600003（ST 东北高速，已退市）。
        # 若源中无该代码，返回空结构，不伪造。
        df = live_provider.get_price("600003.XSHG", "2020-01-01", "2020-12-31")
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_multi_empty_still_multiindex(self, live_provider):
        mp = live_provider.get_price(
            ["600519.XSHG", "600003.XSHG"], "1990-01-01", "1991-01-01"
        )
        assert isinstance(mp, pd.DataFrame)
        assert isinstance(mp.columns, pd.MultiIndex)
        assert len(mp) == 0


@pytest.mark.unit
class TestGetPricePanel:
    def test_multiindex_columns(self, live_provider):
        mp = live_provider.get_price(
            ["600519.XSHG", "000001.XSHE"], "2024-01-02", "2024-01-05"
        )
        assert isinstance(mp, pd.DataFrame)
        assert isinstance(mp.columns, pd.MultiIndex)
        # 第一级 = 字段，第二级 = 证券
        assert set(mp.columns.get_level_values(0)) == set(_PRICE_FIELDS)
        assert set(mp.columns.get_level_values(1)) == {"600519.XSHG", "000001.XSHE"}
        assert len(mp) == 4

    def test_panel_cell_matches_single(self, live_provider):
        single = live_provider.get_price("600519.XSHG", "2024-01-02", "2024-01-03")
        mp = live_provider.get_price(
            ["600519.XSHG", "000001.XSHE"], "2024-01-02", "2024-01-03"
        )
        # (field=close, security=600519.XSHG) 应与单证券一致
        assert mp.loc["2024-01-02", ("close", "600519.XSHG")] == pytest.approx(
            float(single.loc["2024-01-02", "close"])
        )


@pytest.mark.unit
class TestGetPriceReconciliation:
    """强制与原表 final_a_stock_eod_price 抽样对账：数值一致，且绝不读取 adjclose。"""

    def _raw_rows(self, provider, internal, start, end):
        return provider.connection.query(
            "SELECT tradedate, open, high, low, close, volume, amount, adjclose "
            "FROM final_a_stock_eod_price WHERE symbol=%s "
            "AND tradedate >= %s AND tradedate <= %s ORDER BY tradedate ASC",
            (internal, start, end),
        )

    def test_reconcile_single_window(self, live_provider):
        sym = "600519.XSHG"
        internal = normalize_stock_symbol(sym)
        start, end = "2024-01-02", "2024-01-05"
        df = live_provider.get_price(sym, start, end)
        raw = self._raw_rows(live_provider, internal, start, end)

        assert len(df) == len(raw), "返回行数须与原表一致（不增不减）"
        for r in raw:
            d = pd.Timestamp(
                datetime.datetime.combine(r["tradedate"], datetime.time(0, 0))
            )
            for f in _PRICE_FIELDS:
                assert df.loc[d, f] == pytest.approx(float(r[f]), rel=1e-9), (
                    f"字段 {f} 与原表不一致：provider={df.loc[d, f]} raw={r[f]}"
                )

    def test_reconcile_not_using_adjclose(self, live_provider):
        sym = "600519.XSHG"
        internal = normalize_stock_symbol(sym)
        start, end = "2024-01-02", "2024-01-03"
        df = live_provider.get_price(sym, start, end)
        raw = self._raw_rows(live_provider, internal, start, end)
        for r in raw:
            d = pd.Timestamp(
                datetime.datetime.combine(r["tradedate"], datetime.time(0, 0))
            )
            # adjclose 是复权价，与原始 close 相差巨大；确认未误用
            assert abs(df.loc[d, "close"] - float(r["adjclose"])) > 1.0

    def test_reconcile_multi_panel(self, live_provider):
        sym = "000001.XSHE"
        internal = normalize_stock_symbol(sym)
        start, end = "2024-01-02", "2024-01-02"
        mp = live_provider.get_price([sym], start, end)
        raw = self._raw_rows(live_provider, internal, start, end)
        assert len(raw) == 1
        d = pd.Timestamp(
            datetime.datetime.combine(raw[0]["tradedate"], datetime.time(0, 0))
        )
        for f in _PRICE_FIELDS:
            val = mp.loc[d, (f, sym)] if isinstance(mp.columns, pd.MultiIndex) else mp.loc[d, f]
            assert val == pytest.approx(float(raw[0][f]), rel=1e-9)


@pytest.mark.unit
class TestGetPriceLimitAndPaused:
    """涨跌停（high_limit/low_limit）与 paused 派生字段（真实数据，不伪造）。"""

    def test_high_limit_low_limit_from_limit_table(self, live_provider):
        sym = "600519.XSHG"
        internal = normalize_stock_symbol(sym)
        start, end = "2023-01-03", "2023-01-04"
        df = live_provider.get_price(sym, start, end, fields=["high_limit", "low_limit"])
        assert list(df.columns) == ["high_limit", "low_limit"]
        # 与原表 final_a_stock_limit 对账（up_limit / down_limit）
        raw = live_provider._connection.query(
            "SELECT tradedate, up_limit, down_limit FROM final_a_stock_limit "
            "WHERE symbol = %s AND tradedate >= %s AND tradedate <= %s "
            "ORDER BY tradedate ASC",
            (internal, start, end),
        )
        assert len(df) == len(raw)
        for r in raw:
            d = pd.Timestamp(
                datetime.datetime.combine(r["tradedate"], datetime.time(0, 0))
            )
            assert df.loc[d, "high_limit"] == pytest.approx(float(r["up_limit"]), rel=1e-9)
            assert df.loc[d, "low_limit"] == pytest.approx(float(r["down_limit"]), rel=1e-9)

    def test_paused_derived_from_volume(self, live_provider):
        sym = "600519.XSHG"
        start, end = "2023-01-03", "2023-01-04"
        df = live_provider.get_price(sym, start, end, fields=["close", "paused"])
        assert "paused" in df.columns
        # 有成交（volume>0）的交易日 -> paused == False（不伪造停牌）
        assert df["paused"].dtype == bool
        assert (df["paused"] == False).all()  # noqa: E712

    def test_mixed_fields_price_and_limit(self, live_provider):
        sym = "600519.XSHG"
        start, end = "2023-01-03", "2023-01-03"
        df = live_provider.get_price(
            sym, start, end, fields=["open", "close", "high_limit", "low_limit", "paused"]
        )
        assert list(df.columns) == ["open", "close", "high_limit", "low_limit", "paused"]
        assert df.loc[df.index[0], "high_limit"] > df.loc[df.index[0], "close"] > 0
