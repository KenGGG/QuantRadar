def initialize(context):
    context.pool = ['510300.XSHG', '510500.XSHG']
    set_universe(context.pool)
    set_option('avoid_future_data', True)
    set_slippage(FixedSlippage(0.001))
    set_order_cost(OrderCost(open_tax=0, close_tax=0, open_commission=0.0003,
        close_commission=0.0003, min_commission=5), type='fund')
    run_monthly(rebalance, monthday=1, time='09:30', force=False)

def rebalance(context):
    scores = {}
    for security in context.pool:
        history = attribute_history(security, 21, '1d', ['close'], df=True)
        if len(history) != 21: raise ValueError('Expected 21 warmup bars: '+security)
        scores[security] = history.close.iloc[-1] / history.close.iloc[0] - 1
    winner = max(scores, key=scores.get)
    log.info('Monthly fixed ETF pool winner='+winner+' scores='+str(scores))
    for security in context.pool:
        if security != winner: order_target(security, 0)
    order_target_value(winner, context.portfolio.total_value * 0.8)
