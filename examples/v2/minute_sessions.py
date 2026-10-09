def initialize(context):
    context.security = '510300.XSHG'
    context.bought = False
    context.callbacks = []
    set_universe([context.security])
    set_option('avoid_future_data', True)
    set_slippage(FixedSlippage(0.001))
    set_order_cost(OrderCost(open_tax=0, close_tax=0, open_commission=0.0003,
        close_commission=0.0003, min_commission=5), type='fund')
    run_daily(on_minute, time='every_minute')
    run_daily(on_close, time='15:00')

def before_trading_start(context):
    context.callbacks = []
    history = attribute_history(context.security, 3, '1d', ['close'], df=True)
    if len(history) != 3: raise ValueError('Minute strategy warmup missing')
    log.info('PREMARKET '+str(context.current_dt))

def on_minute(context):
    stamp = context.current_dt.strftime('%H:%M')
    context.callbacks.append(stamp)
    log.info('MINUTE_CALLBACK '+str(context.current_dt))
    if stamp == '09:31' and not context.bought:
        order_target(context.security, 1000)
        context.bought = True
    if str(context.current_dt.date()) == context.run_params['extras']['exit_date'] and stamp == '09:32':
        order_target(context.security, 0)

def on_close(context):
    assert len(context.callbacks) == 240
    assert context.callbacks[0] == '09:30'
    assert context.callbacks[119:121] == ['11:29', '13:00']
    assert context.callbacks[-1] == '14:59'
    log.info('SESSION_CHECK callbacks=240 open=09:30 lunch=11:29/13:00 last=14:59 close='+str(context.current_dt))
