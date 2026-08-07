from jqdata import *
from datetime import datetime, timedelta

def initialize(context):
    set_benchmark('000300.XSHG')
    set_option("avoid_future_data", True)
    
    set_option('use_real_price', True)
    g.target = ['000001.XSHE', '600000.XSHG']
    run_daily(market_open, time='10:00')

def market_open(context):
    for stock in g.target:
        print(stock, get_previous_minute_price(stock, context))


# ==================== 辅助函数：价格获取 ====================
def get_previous_minute_price(security, context):
    """
    获取前一分钟的价格，避免未来函数问题的关键函数
    
    关键修复：使用前1分钟的价格而不是当前价格，确保没有未来数据
    
    实现原理：
    1. 获取前2分钟到当前时间的分钟数据
    2. 取倒数第二根K线作为前1分钟的价格
    3. 如果分钟数据不足，则使用日线数据的昨天收盘价
    
    Parameters:
    security: 证券代码
    context: 策略上下文
    
    Returns:
    float: 前1分钟的价格，如果获取失败则返回0
    """
    try:
        # 获取前1分钟的分钟数据
        # 注意：如果当前是9:31，前1分钟就是9:30的数据
        end_time = context.current_dt
        start_time = end_time - timedelta(minutes=2)  # 多取1分钟确保有数据
        
        # 获取分钟数据
        minute_data = get_price(
            security, 
            start_date=start_time, 
            end_date=end_time, 
            frequency='1m', 
            fields=['close'],
            skip_paused=False,
            fq='pre',
            panel=False
        )
        
        # 如果分钟数据不足，使用日线数据
        if minute_data is None or len(minute_data) < 2:
            # 使用日线数据的昨天收盘价
            hist_data = attribute_history(security, 2, '1d', ['close'], skip_paused=True)
            if not hist_data.empty:
                return hist_data['close'].iloc[-1]
            return 0
        
        # 获取前1分钟的收盘价（倒数第二根K线）
        # 最后一根K线是当前分钟的，可能不完整
        if len(minute_data) >= 2:
            return minute_data['close'].iloc[-2]
        else:
            return minute_data['close'].iloc[-1]
            
    except Exception as e:
        log.warn(f"获取{security}前1分钟价格失败: {e}")
        # 失败时返回0，后续会处理
        return 0

