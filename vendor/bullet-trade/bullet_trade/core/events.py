"""
事件定义模块

定义 bullet_trade 中使用的各类事件
"""

from .event_bus import Event, EventPriority


# ============ 回测事件 ============

class BacktestEvent(Event):
    """回测事件基类"""
    priority = EventPriority.DEFAULT


class BacktestStartEvent(BacktestEvent):
    """
    回测开始事件
    
    Attributes:
        start_date: 开始日期
        end_date: 结束日期
        initial_cash: 初始资金
    """
    pass


class BacktestEndEvent(BacktestEvent):
    """
    回测结束事件
    
    Attributes:
        total_returns: 总收益率
        final_value: 最终价值
    """
    pass


class TradingDayStartEvent(BacktestEvent):
    """
    交易日开始事件
    
    Attributes:
        date: 交易日日期
    """
    priority = EventPriority.BACK_TEST_RECORD


class TradingDayEndEvent(BacktestEvent):
    """
    交易日结束事件
    
    Attributes:
        date: 交易日日期
        portfolio_value: 当日组合价值
    """
    priority = EventPriority.BACK_TEST_RECORD


# ============ 市场事件 ============

class MarketEvent(Event):
    """市场事件基类"""
    priority = EventPriority.DEFAULT


class BeforeTradingStartEvent(MarketEvent):
    """
    盘前事件（每个交易日开盘前触发）
    
    Attributes:
        date: 日期
    """
    priority = EventPriority.DEFAULT


class MarketOpenEvent(MarketEvent):
    """
    开盘事件
    
    Attributes:
        time: 开盘时间
    """
    priority = EventPriority.EVERY_MINUTE


class MarketCloseEvent(MarketEvent):
    """
    收盘事件
    
    Attributes:
        time: 收盘时间
    """
    priority = EventPriority.DEFAULT


class AfterTradingEndEvent(MarketEvent):
    """
    盘后事件（每天收盘后触发）
    
    Attributes:
        date: 日期
    """
    priority = EventPriority.DEFAULT


class EveryBarEvent(MarketEvent):
    """
    每个 Bar 事件（tick/minute/day）
    
    Attributes:
        time: 时间
        frequency: 频率（'tick', 'minute', 'day'）
    """
    priority = EventPriority.EVERY_MINUTE


class EveryMinuteEvent(MarketEvent):
    """
    每分钟事件
    
    Attributes:
        time: 时间
    """
    priority = EventPriority.EVERY_MINUTE


# ============ 订单事件 ============

class OrderEvent(Event):
    """订单事件基类"""
    priority = EventPriority.DEFAULT


class OrderCreatedEvent(OrderEvent):
    """
    订单创建事件
    
    Attributes:
        order_id: 订单ID
        security: 标的代码
        amount: 数量
        price: 价格
    """
    pass


class OrderFilledEvent(OrderEvent):
    """
    订单成交事件
    
    Attributes:
        order_id: 订单ID
        filled_amount: 成交数量
        filled_price: 成交价格
    """
    pass


class OrderCanceledEvent(OrderEvent):
    """
    订单取消事件
    
    Attributes:
        order_id: 订单ID
        reason: 取消原因
    """
    pass


class OrderRejectedEvent(OrderEvent):
    """
    订单拒绝事件
    
    Attributes:
        order_id: 订单ID
        reason: 拒绝原因
    """
    pass


# ============ 账户事件 ============

class AccountEvent(Event):
    """账户事件基类"""
    priority = EventPriority.ACCOUNT_SYNC


class AccountSyncEvent(AccountEvent):
    """
    账户同步事件（定时触发）
    
    Attributes:
        timestamp: 同步时间戳
    """
    priority = EventPriority.ACCOUNT_SYNC


class PositionChangedEvent(AccountEvent):
    """
    持仓变化事件
    
    Attributes:
        security: 标的代码
        old_amount: 原持仓数量
        new_amount: 新持仓数量
    """
    pass


class CashChangedEvent(AccountEvent):
    """
    现金变化事件
    
    Attributes:
        old_cash: 原现金
        new_cash: 新现金
        reason: 变化原因
    """
    pass


# ============ 数据事件 ============

class DataEvent(Event):
    """数据事件基类"""
    priority = EventPriority.DEFAULT


class DataUpdateEvent(DataEvent):
    """
    数据更新事件
    
    Attributes:
        securities: 更新的标的列表
        data_type: 数据类型（'price', 'fundamental' 等）
    """
    pass


class DataErrorEvent(DataEvent):
    """
    数据错误事件
    
    Attributes:
        security: 标的代码
        error: 错误信息
    """
    pass


# ============ 系统事件 ============

class SystemEvent(Event):
    """系统事件基类"""
    priority = EventPriority.DEFAULT


class SystemStartEvent(SystemEvent):
    """系统启动事件"""
    pass


class SystemStopEvent(SystemEvent):
    """系统停止事件"""
    pass


class SystemErrorEvent(SystemEvent):
    """
    系统错误事件
    
    Attributes:
        error: 错误信息
        traceback: 错误堆栈
    """
    pass


class GlobalDataSyncEvent(SystemEvent):
    """
    全局变量同步事件（持久化）
    
    Attributes:
        variables: 要同步的变量字典
    """
    priority = EventPriority.GLOBAL_DATA_SYNC


# ============ 调度事件 ============

class ScheduleEvent(Event):
    """调度事件基类"""
    priority = EventPriority.DEFAULT


class DailyTaskEvent(ScheduleEvent):
    """
    每日任务事件
    
    Attributes:
        task_name: 任务名称
        time_expr: 时间表达式（如 'open', 'close', '09:30:00'）
    """
    pass


class WeeklyTaskEvent(ScheduleEvent):
    """
    每周任务事件
    
    Attributes:
        task_name: 任务名称
        weekday: 星期几（0=周一, 6=周日）
        time_expr: 时间表达式
    """
    pass


class MonthlyTaskEvent(ScheduleEvent):
    """
    每月任务事件
    
    Attributes:
        task_name: 任务名称
        day: 日期（1-31）
        time_expr: 时间表达式
    """
    pass


# ============ 实盘事件 ============

class LiveTradingEvent(Event):
    """实盘交易事件基类"""
    priority = EventPriority.DEFAULT


class OrdersSyncEvent(LiveTradingEvent):
    """
    订单同步事件（实盘）
    
    Attributes:
        order_ids: 同步的订单ID列表
    """
    priority = EventPriority.ORDERS_SYNC


class TradeGateBeforeOpenEvent(LiveTradingEvent):
    """
    交易接口盘前事件
    
    Attributes:
        date: 日期
    """
    priority = EventPriority.BACK_TEST_RECORD


class TradeGateAfterCloseEvent(LiveTradingEvent):
    """
    交易接口盘后事件
    
    Attributes:
        date: 日期
    """
    priority = EventPriority.BACK_TEST_RECORD
