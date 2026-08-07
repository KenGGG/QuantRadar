"""
JQData 数据模块
"""
from .api import (
    get_price, attribute_history, get_current_data,
    get_trade_days, get_all_securities, get_index_stocks,
    set_data_provider, get_data_provider
)

# 提供兼容的 auth 接口，委托给当前数据提供者

def auth(user: str = None, pwd: str = None, host: str = None, port: int = None):
    return get_data_provider().auth(user=user, pwd=pwd, host=host, port=port)

__all__ = [
    'auth',
    'get_price',
    'attribute_history',
    'get_current_data',
    'get_trade_days',
    'get_all_securities',
    'get_index_stocks',
    'set_data_provider',
    'get_data_provider',
]

