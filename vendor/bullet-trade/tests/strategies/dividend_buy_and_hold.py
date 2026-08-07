"""
双标的买入持有策略，聚焦分红处理验证。

策略说明：
1. 回测起始日首个交易日（2015-01-01 之后的第一个交易日）买入两只标的：
   - 银华日利货币 ETF（511880.XSHG），占用一半资金
   - 中国平安（601318.XSHG），占用另一半资金
2. 采用 `use_real_price=True`，确保下单价格为当日真实价格（动态前复权）。
3. 之后不再调仓或再投资，持有到 2025-01-01。
"""
from jqdata import *


SILVER_MONETARY_FUND = "511880.XSHG"
PINGAN_STOCK = "601318.XSHG"


def initialize(context):
    """初始化策略，记录目标标的并注册调度。"""
    set_benchmark("000300.XSHG")
    set_option("use_real_price", True)

    g.targets = (
        (SILVER_MONETARY_FUND, 0.5),
        (PINGAN_STOCK, 0.5),
    )
    g.has_bought = False

    run_daily(market_open, time="open")
    run_daily(market_close, time="close")

def market_close(context):
    #if context.current_dt.date() != datetime.date(2024,12,31):
    # log.info(f"total: {context.portfolio.total_value} cash:{context.portfolio.available_cash}")
    # log.info(f"position value: {context.portfolio.positions_value}")
    # for code in context.portfolio.positions.keys():
    #     pos = context.portfolio.positions[code]
    #     price = get_current_data()[code].last_price
    #     log.info(f"code:{code} amount: {pos.total_amount} price: {price} value: {pos.total_amount * price}")

    print_portfolio_info(context, top_n=10)
            
def market_open(context):
    """首个交易日开盘按目标权重买入两只标的。"""
    if g.has_bought:
        if context.current_dt.date() == datetime.date(2025,1,10):
            for security, weight in g.targets:
                order_target_value(security, 1000)
        return

    available_cash = context.portfolio.available_cash
    for security, weight in g.targets:
        allocation = available_cash * weight
        if allocation <= 0:
            continue
        order_value(security, allocation)
        log.info(f"下单 {security}，金额 {allocation:.2f}")

    g.has_bought = True
    
    #log.info(f"{context.current_dt.date()} {type(context.current_dt)} {context.current_dt.date() == datetime.date(2015,1,5)}")
    #if context.current_dt != datetime.date(2024,12,31):
    #if context.current_dt.date() != datetime.date(2024,12,31):
    #    return 


