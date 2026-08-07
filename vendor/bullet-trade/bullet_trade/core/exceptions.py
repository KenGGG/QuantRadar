"""
异常定义

定义回测系统使用的异常类
"""


class FutureDataError(Exception):
    """
    未来数据错误
    
    当启用 avoid_future_data 后，如果尝试访问未来数据会抛出此异常
    """
    pass


class UserError(Exception):
    """
    用户错误
    
    用户使用API时的错误
    """
    pass


__all__ = ['FutureDataError', 'UserError']

