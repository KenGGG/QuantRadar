"""
用户自定义策略 a.py

这是一个示例文件，展示如何快速创建和测试策略。
你可以直接修改此文件，或者创建新的策略文件。

注意：回测配置在 tests/strategies/config.yaml 中定义
"""
from jqdata import *


def initialize(context):
    """
    初始化策略
    
    在这里设置你的策略参数和调度
    """
    # 设置基准
    set_benchmark('000300.XSHG')
    
    # 设置要交易的股票
    g.stock = '000001.XSHE'  # 平安银行
    
    # 每天开盘时执行交易逻辑
    run_daily(market_open, time='open')


def market_open(context):
    """
    每天开盘时调用
    
    在这里编写你的交易逻辑
    """
    stock = g.stock
    
    # 获取最近10天的数据
    df = get_price(
        stock,
        end_date=context.current_dt,
        count=10,
        fields=['close', 'volume']
    )
    
    if df is None or len(df) < 10:
        return
    
    # 获取当前价格
    current_price = df['close'].iloc[-1]
    
    # 简单策略：如果当前没有持仓，就买入
    if stock not in context.portfolio.positions:
        # 用一半的资金买入
        cash_to_use = context.portfolio.available_cash * 0.5
        order_value(stock, cash_to_use)
        log.info(f"买入 {stock}，价格: {current_price:.2f}，金额: {cash_to_use:.2f}")
    
    else:
        # 如果已持仓，获取持仓信息
        position = context.portfolio.positions[stock]
        
        # 简单止盈止损：盈利超过5%或亏损超过3%就卖出
        profit_ratio = (current_price - position.avg_cost) / position.avg_cost
        
        if profit_ratio > 0.05:
            order_target(stock, 0)
            log.info(f"止盈卖出 {stock}，盈利: {profit_ratio:.2%}")
        
        elif profit_ratio < -0.03:
            order_target(stock, 0)
            log.info(f"止损卖出 {stock}，亏损: {profit_ratio:.2%}")

