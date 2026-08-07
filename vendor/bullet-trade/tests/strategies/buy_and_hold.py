"""
买入持有策略示例

策略逻辑：
1. 第一天买入沪深300ETF（510300.XSHG）
2. 一直持有到回测结束
3. 用于测试基本的买卖功能

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
    
    # 设置要交易的股票
    g.stock = '510300.XSHG'  # 沪深300ETF
    
    # 记录是否已经买入
    g.has_bought = False
    
    # 每天开盘时执行
    run_daily(market_open, time='open')


def market_open(context):
    """
    开盘时执行
    
    Args:
        context: 策略上下文
    """
    # 只在第一天买入
    if not g.has_bought:
        # 全仓买入
        order_value(g.stock, context.portfolio.available_cash)
        g.has_bought = True
        
        log.info(f"买入 {g.stock}，金额: {context.portfolio.available_cash:.2f}")

