"""symbols.py 单元测试（纯函数，无需数据库）。"""

import pytest

from quantradar.providers.investment_data.symbols import (
    SymbolError,
    normalize_index_symbol,
    normalize_stock_symbol,
    to_investment_data_symbol,
    to_joinquant_index_symbol,
    to_joinquant_symbol,
    to_ts_symbol,
)


@pytest.mark.unit
class TestStockNormalize:
    def test_internal_format_passthrough(self):
        assert normalize_stock_symbol("SH600519") == "SH600519"
        assert normalize_stock_symbol("SZ000001") == "SZ000001"

    def test_ts_format(self):
        assert normalize_stock_symbol("600519.SH") == "SH600519"
        assert normalize_stock_symbol("000001.SZ") == "SZ000001"

    def test_joinquant_format(self):
        assert normalize_stock_symbol("600519.XSHG") == "SH600519"
        assert normalize_stock_symbol("000001.XSHE") == "SZ000001"

    def test_to_joinquant(self):
        assert to_joinquant_symbol("SH600519") == "600519.XSHG"
        assert to_joinquant_symbol("SZ000001") == "000001.XSHE"

    def test_to_ts(self):
        assert to_ts_symbol("SH600519") == "600519.SH"
        assert to_ts_symbol("600519.XSHG") == "600519.SH"

    def test_to_investment_data_alias(self):
        assert to_investment_data_symbol("000001.XSHE") == "SZ000001"


@pytest.mark.unit
class TestIndexNormalize:
    def test_jq_to_ts(self):
        assert normalize_index_symbol("000300.XSHG") == "000300.SH"
        assert normalize_index_symbol("399300.XSHE") == "399300.SZ"

    def test_ts_passthrough(self):
        assert normalize_index_symbol("000300.SH") == "000300.SH"

    def test_to_joinquant_index(self):
        assert to_joinquant_index_symbol("000300.SH") == "000300.XSHG"
        assert to_joinquant_index_symbol("399300.SZ") == "399300.XSHE"


@pytest.mark.unit
class TestInvalid:
    def test_none(self):
        with pytest.raises(SymbolError):
            normalize_stock_symbol(None)

    def test_empty(self):
        with pytest.raises(SymbolError):
            normalize_stock_symbol("")

    def test_bare_numeric_ambiguous(self):
        # 裸 6 位数字缺交易所，无法判定 SH/SZ -> 拒绝（不猜测）
        with pytest.raises(SymbolError):
            normalize_stock_symbol("600519")

    def test_garbage(self):
        with pytest.raises(SymbolError):
            normalize_stock_symbol("NOTACODE")

    def test_index_garbage(self):
        with pytest.raises(SymbolError):
            normalize_index_symbol("600519")

    def test_whitespace_normalized(self):
        assert normalize_stock_symbol("  600519.XSHG  ") == "SH600519"
