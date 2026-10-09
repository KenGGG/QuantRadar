def initialize(context):
    context.security = '600519.XSHG'
    set_universe([context.security])
    set_benchmark('000300.XSHG')
    set_option('avoid_future_data', True)
    set_order_cost(OrderCost(open_tax=0, close_tax=0.0005,
        open_commission=0.0003, close_commission=0.0003, min_commission=5), type='stock')

def handle_data(context, data):
    if not context.portfolio.positions:
        order_target(context.security, 100)
        log.info('Buy and hold: simulated position opened')
