"""
简单均线策略示例

策略逻辑：
1. 选择沪深300成分股中流动性好的前10只股票
2. 当股价上穿5日均线时买入
3. 当股价下穿5日均线时卖出
4. 每只股票最多持仓10%

注意：回测配置在 tests/strategies/config.yaml 中定义
"""
from jqdata import *


def initialize(context):
    """
    初始化策略
    
    Args:
        context: 策略上下文
    """
    # 设置基准
    set_benchmark('000300.XSHG')
    
    # 开启真实价格和避免未来数据
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)
    
    # 设置滑点和手续费
    set_slippage(FixedSlippage(0.002))  # 0.2% 滑点
    set_order_cost(OrderCost(
        open_tax=0,
        close_tax=0.001,      # 卖出印花税 0.1%
        open_commission=0.0003,  # 买入佣金 0.03%
        close_commission=0.0003,  # 卖出佣金 0.03%
        min_commission=5      # 最低佣金 5元
    ), type='stock')
    
    # 初始化股票池
    context.stock_pool = []
    context.ma_period = 5  # 均线周期
    
    # 每天开盘前更新股票池
    run_daily(before_market_open, time='before_open')
    
    # 每天开盘时执行交易
    run_daily(market_open, time='open')


def before_market_open(context):
    """
    开盘前准备
    
    Args:
        context: 策略上下文
    """
    # 获取沪深300成分股
    hs300_stocks = get_index_stocks('000300.XSHG')
    
    # 获取过去20天的成交额数据
    # 注意：
    # 1. 传入多个股票时，需要设置 panel=False 才能返回 DataFrame 格式
    #    否则会返回 Panel 对象（已废弃），无法使用 groupby 操作
    # 2. 开盘前不能获取当日的 money 字段数据（聚宽限制）
    #    因此使用 end_date=context.previous_date 和 count，确保不包含当日数据
    df = get_price(
        hs300_stocks,
        end_date=context.previous_date,  # 使用前一交易日作为结束日期
        count=20,  # 从前一交易日往前推 20 条数据
        fields=['money'],
        panel=False  # 设置为 False 返回 DataFrame，包含 code 列
    )
    
    if df is not None and not df.empty:
        # 计算平均成交额
        avg_money = df.groupby('code')['money'].mean()
        
        # 选择成交额最大的前10只股票
        context.stock_pool = avg_money.nlargest(10).index.tolist()
        
        log.info(f"更新股票池: {context.stock_pool}")


def market_open(context):
    """
    开盘时执行交易
    
    Args:
        context: 策略上下文
    """
    # 获取当前持仓
    current_positions = list(context.portfolio.positions.keys())
    
    # 遍历股票池
    for stock in context.stock_pool:
        # 获取历史数据（需要足够的数据计算均线）
        # 注意：盘中不能获取当日的 close 字段数据（聚宽限制）
        # 因此使用 end_date=context.previous_date，确保不包含当日数据
        df = get_price(
            stock,
            end_date=context.previous_date,  # 使用前一交易日作为结束日期
            count=context.ma_period + 1,
            fields=['close']
        )
        
        if df is None or len(df) < context.ma_period + 1:
            continue
        
        # 计算5日均线
        ma5 = df['close'].rolling(window=context.ma_period).mean()
        
        # 获取当前价格和前一日价格
        current_price = df['close'].iloc[-1]
        prev_price = df['close'].iloc[-2]
        
        # 获取当前和前一日的均线
        current_ma = ma5.iloc[-1]
        prev_ma = ma5.iloc[-2]
        
        # 判断是否持仓
        is_holding = stock in current_positions
        
        # 买入信号：前一日价格 < 前一日均线，当前价格 > 当前均线（上穿）
        if not is_holding and prev_price < prev_ma and current_price > current_ma:
            # 买入，使用10%的资金
            order_value(stock, context.portfolio.total_value * 0.1)
            log.info(f"买入信号: {stock}, 价格={current_price:.2f}, MA5={current_ma:.2f}")
        
        # 卖出信号：前一日价格 > 前一日均线，当前价格 < 当前均线（下穿）
        elif is_holding and prev_price > prev_ma and current_price < current_ma:
            # 卖出全部持仓
            order_target(stock, 0)
            log.info(f"卖出信号: {stock}, 价格={current_price:.2f}, MA5={current_ma:.2f}")

