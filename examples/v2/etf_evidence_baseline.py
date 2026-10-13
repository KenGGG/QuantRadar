"""Predeclared research controls. Never connect to a trading account."""
import builtins as _py
import numpy as np

def initialize(context):
    context.pool = ['512890.XSHG', '159949.XSHE', '513100.XSHG', '518880.XSHG']
    context.params = {'mode':'hold', 'security':'159949.XSHE', 'earliest':'2019-05-29'}
    context.params.update(context.run_params.get('extras') or {})
    context.month = None
    set_universe(context.pool)
    set_option('avoid_future_data', True)
    set_slippage(FixedSlippage(0.001))
    set_order_cost(OrderCost(open_tax=0, close_tax=0, open_commission=0.0003,
                            close_commission=0.0003, min_commission=5), type='fund')
    run_daily(rebalance, time='09:30')

def rebalance(context):
    if str(context.current_dt.date()) < context.params['earliest']:
        return
    mode = context.params['mode']
    held = [s for s in context.pool if s in context.portfolio.positions
            and context.portfolio.positions[s].total_amount > 0]
    if mode == 'equal':
        month = str(context.current_dt.date())[:7]
        if context.month == month:
            return
        capital = context.portfolio.total_value
        target = capital * 0.99 / len(context.pool)
        # Reductions precede increases; do not assume partial fills succeeded.
        for s in context.pool:
            pos = context.portfolio.positions.get(s)
            if pos and pos.value > target:
                order_target_value(s, target)
        for s in context.pool:
            pos = context.portfolio.positions.get(s)
            if not pos or pos.value < target:
                order_target_value(s, target)
        context.month = month
        return
    target = context.params['security']
    if mode == 'momentum':
        scores = {}
        for s in context.pool:
            bars = attribute_history(s, 26, '1d', ['close'], skip_paused=False, df=True, fq='pre')
            values = np.asarray(bars.close, dtype=float)
            if len(values) != 26 or not np.isfinite(values).all() or (values <= 0).any():
                raise ValueError('Missing prior-day momentum data: '+s)
            scores[s] = float(values[-1]/values[0]-1)
        target = _py.max(scores, key=scores.get)
    for s in held:
        if s != target:
            order_target(s, 0)
    if _py.any(s != target and s in context.portfolio.positions
               and context.portfolio.positions[s].total_amount > 0 for s in held):
        return
    if target not in held:
        order_target_value(target, context.portfolio.total_value * 0.99)
