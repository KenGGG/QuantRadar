"""InvestmentDataProvider 包。

统一从本模块导出，便于：
    from quantradar.providers.investment_data import InvestmentDataProvider
"""

from .capabilities import CAPABILITIES, capability_summary
from .connection import (
    InvestmentDataConnection,
    InvestmentDataConnectionError,
    connect,
)
from .provider import InvestmentDataProvider
from .symbols import (
    SymbolError,
    normalize_index_symbol,
    normalize_stock_symbol,
    to_investment_data_symbol,
    to_joinquant_index_symbol,
    to_joinquant_symbol,
    to_ts_symbol,
)

__all__ = [
    "InvestmentDataProvider",
    "InvestmentDataConnection",
    "InvestmentDataConnectionError",
    "connect",
    "SymbolError",
    "normalize_stock_symbol",
    "normalize_index_symbol",
    "to_ts_symbol",
    "to_joinquant_symbol",
    "to_joinquant_index_symbol",
    "to_investment_data_symbol",
    "CAPABILITIES",
    "capability_summary",
]
