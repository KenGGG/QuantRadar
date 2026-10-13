"""Article reproduction with explicit research assumptions; not trading code."""
import numpy as np
import pandas as pd


def bias_factor(close, bias_n, momentum_n):
    close = pd.Series(close, dtype=float)
    bias = close / close.rolling(bias_n, min_periods=1).mean()
    y = bias.iloc[-momentum_n:].to_numpy()
    return float(np.polyfit(np.arange(len(y)), y / y[0], 1)[0] * 10000)


def slope_factor(close, slope_n):
    y = np.asarray(close, dtype=float)[-slope_n:]
    y = y / y[0]
    x = np.arange(1, len(y) + 1)
    slope, intercept = np.polyfit(x, y, 1)
    total = np.sum((y - y.mean())**2)
    r2 = 0.0 if total == 0 else 1 - np.sum((y - (slope*x + intercept))**2) / total
    return float(10000 * slope * r2)


def efficiency_factor(history, efficiency_n):
    pivot = history[['open', 'high', 'low', 'close']].iloc[-efficiency_n:].mean(axis=1)
    logs = np.log(pivot.to_numpy(dtype=float))
    change = logs[-1] - logs[0]
    volatility = np.abs(np.diff(logs)).sum()
    return float(100 * change * (abs(change) / volatility if volatility else 0))


def combine_factors(factors, weights):
    keys = list(factors)
    matrix = np.asarray([factors[key] for key in keys], dtype=float)
    sigma = matrix.std(axis=0, ddof=0)
    z = np.divide(matrix - matrix.mean(axis=0), sigma, out=np.zeros_like(matrix), where=sigma != 0)
    return dict(zip(keys, (z @ np.asarray(weights, dtype=float)).tolist()))


def choose_target(scores, current, switch_ratio):
    winner = max(scores, key=scores.get)
    if current not in scores:
        return winner
    # Keep ties, including zero/negative ties; literal 1.5x for strict leaders.
    if winner != current and scores[winner] > scores[current] and scores[winner] > scores[current] * switch_ratio:
        return winner
    return current


def score_history(history, params, today):
    required = max(params['bias_n'] + params['momentum_n'] - 1, params['slope_n'], params['efficiency_n'])
    if len(history) != required:
        raise ValueError('Expected full warmup: ' + str(required))
    index = pd.DatetimeIndex(history.index)
    if not index.is_monotonic_increasing or not index.is_unique or any(index.date >= today):
        raise ValueError('History must contain unique increasing prior-day bars')
    ohlc = history[['open', 'high', 'low', 'close']].to_numpy(dtype=float)
    if not np.isfinite(ohlc).all() or (ohlc <= 0).any():
        raise ValueError('OHLC must be positive finite')
    return [bias_factor(history.close, params['bias_n'], params['momentum_n']),
            slope_factor(history.close, params['slope_n']),
            efficiency_factor(history, params['efficiency_n'])]


def initialize(context):
    context.pool = ['512890.XSHG', '159949.XSHE', '513100.XSHG', '518880.XSHG']
    context.params = dict(bias_n=60, momentum_n=25, slope_n=25, efficiency_n=25,
                          weights=[0.3, 0.3, 0.4], switch_ratio=1.5, allocation=0.99)
    extras = context.run_params.get('extras') or {}
    if set(extras) - set(context.params):
        raise ValueError('Unknown research parameter')
    context.params.update(extras)
    p = context.params
    for key in ['bias_n', 'momentum_n', 'slope_n', 'efficiency_n']:
        if type(p[key]) is not int or p[key] < 2:
            raise ValueError('Window parameter must be integer >= 2: ' + key)
    weights = np.asarray(p['weights'], dtype=float)
    if weights.shape != (3,) or not np.isfinite(weights).all() or (weights < 0).any() or not np.isclose(weights.sum(), 1):
        raise ValueError('Weights parameter must be three nonnegative finite values summing to one')
    if not np.isfinite(p['switch_ratio']) or p['switch_ratio'] < 1 or not np.isfinite(p['allocation']) or not 0 < p['allocation'] <= 1:
        raise ValueError('Invalid switch_ratio/allocation parameter')
    set_universe(context.pool)
    set_option('avoid_future_data', True)
    set_slippage(FixedSlippage(0.001))
    set_order_cost(OrderCost(open_tax=0, close_tax=0, open_commission=0.0003,
                            close_commission=0.0003, min_commission=5), type='fund')
    run_daily(rebalance, time='09:30')


def rebalance(context):
    p = context.params
    count = max(p['bias_n'] + p['momentum_n'] - 1, p['slope_n'], p['efficiency_n'])
    factors = {}
    for security in context.pool:
        history = attribute_history(security, count, '1d', ['open','high','low','close'],
                                    skip_paused=False, df=True, fq='pre')
        if len(history) < count:
            if getattr(context, 'warmup_complete', False):
                raise ValueError('ETF3 history lost after warmup: ' + security)
            log.info('ETF3 warmup pending ' + security + ': ' + str(len(history)) + '/' + str(count))
            return
        factors[security] = score_history(history, p, context.current_dt.date())
    context.warmup_complete = True
    scores = combine_factors(factors, p['weights'])
    held = [s for s in context.pool if s in context.portfolio.positions and context.portfolio.positions[s].total_amount > 0]
    current = held[0] if held else None
    target = choose_target(scores, current, p['switch_ratio'])
    log.info('ETF3 scores=' + str(scores) + ' current=' + str(current) + ' target=' + target)
    for security in held:
        if security != target:
            order_target(security, 0)
    if any(s != target and s in context.portfolio.positions and context.portfolio.positions[s].total_amount > 0 for s in held):
        log.info('ETF3 liquidation incomplete; no second ETF purchase')
        return
    if target != current:
        order_target_value(target, context.portfolio.total_value * p['allocation'])
