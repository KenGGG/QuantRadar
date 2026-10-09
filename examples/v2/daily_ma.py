def initialize(context):
    context.security = '510300.XSHG'
    set_universe([context.security])
    set_option('avoid_future_data', True)
    set_slippage(FixedSlippage(0.001))
    set_order_cost(OrderCost(open_tax=0, close_tax=0, open_commission=0.0003,
        close_commission=0.0003, min_commission=5), type='fund')
    run_daily(rebalance, time='09:30')

def rebalance(context):
    history = attribute_history(context.security, 10, '1d', ['close'], df=True)
    if len(history) != 10: raise ValueError('Expected ten warmup bars')
    fast = history.close.tail(3).mean()
    slow = history.close.mean()
    log.info('MA warmup=%s fast=%.6f slow=%.6f' % (len(history), fast, slow))
    target = context.portfolio.total_value * 0.8 if fast > slow else 0
    order_target_value(context.security, target)
