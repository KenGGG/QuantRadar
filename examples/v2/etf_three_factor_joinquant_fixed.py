"""Article reproduction with explicit research assumptions; not trading code."""
import builtins as _py
import numpy as np
import pandas as pd


def bias_factor(close, bias_n, momentum_n):
    close = pd.Series(close, dtype=float)
    bias = close / close.rolling(bias_n, min_periods=1).mean()
    y = np.asarray(bias.iloc[-momentum_n:].values, dtype=float)
    return float(np.polyfit(np.arange(len(y)), y / y[0], 1)[0] * 10000)


def slope_factor(close, slope_n):
    y = np.asarray(close, dtype=float)[-slope_n:]
    y = y / y[0]
    x = np.arange(1, len(y) + 1)
    slope, intercept = np.polyfit(x, y, 1)
    total = np.sum((y - y.mean()) ** 2)
    r2 = (
        0.0
        if total == 0
        else 1 - np.sum((y - (slope * x + intercept)) ** 2) / total
    )
    return float(10000 * slope * r2)


def efficiency_factor(history, efficiency_n):
    pivot = (
        history[['open', 'high', 'low', 'close']]
        .iloc[-efficiency_n:]
        .mean(axis=1)
    )
    logs = np.log(np.asarray(pivot.values, dtype=float))
    change = logs[-1] - logs[0]
    volatility = np.abs(np.diff(logs)).sum()
    return float(
        100 * change * (abs(change) / volatility if volatility else 0)
    )


def combine_factors(factors, weights):
    keys = list(factors)
    matrix = np.asarray([factors[key] for key in keys], dtype=float)
    sigma = matrix.std(axis=0, ddof=0)
    z = np.divide(
        matrix - matrix.mean(axis=0),
        sigma,
        out=np.zeros_like(matrix),
        where=sigma != 0,
    )
    return dict(zip(keys, (z @ np.asarray(weights, dtype=float)).tolist()))


def choose_target(scores, current, switch_ratio):
    winner = _py.max(scores, key=scores.get)
    if current not in scores:
        return winner

    # 平分时保持当前持仓，切换规则沿用原策略。
    if (
        winner != current
        and scores[winner] > scores[current]
        and scores[winner] > scores[current] * switch_ratio
    ):
        return winner

    return current


def score_history(history, params, today, security='unknown'):
    required = _py.max(
        params['bias_n'] + params['momentum_n'] - 1,
        params['slope_n'],
        params['efficiency_n'],
    )
    if len(history) != required:
        raise ValueError(
            'Expected full warmup: security=%s expected=%s actual=%s'
            % (security, required, len(history))
        )

    index = pd.DatetimeIndex(history.index)
    if (
        not index.is_monotonic_increasing
        or not index.is_unique
        or _py.any(index.date >= today)
    ):
        raise ValueError(
            'History must contain unique increasing prior-day bars: '
            + security
        )

    fields = ['open', 'high', 'low', 'close']
    ohlc = np.asarray(history[fields].values, dtype=float)
    invalid = (~np.isfinite(ohlc)) | (ohlc <= 0)

    if invalid.any():
        locations = np.argwhere(invalid)
        details = []
        for row, col in locations[:10]:
            details.append(
                '%s %s=%s'
                % (
                    str(history.index[row]),
                    fields[col],
                    str(ohlc[row, col]),
                )
            )

        raise ValueError(
            'Invalid OHLC: security=%s today=%s invalid_cells=%s details=%s'
            % (
                security,
                str(today),
                len(locations),
                '; '.join(details),
            )
        )

    return [
        bias_factor(history.close, params['bias_n'], params['momentum_n']),
        slope_factor(history.close, params['slope_n']),
        efficiency_factor(history, params['efficiency_n']),
    ]


def initialize(context):
    context.pool = [
        '512890.XSHG',
        '159949.XSHE',
        '513100.XSHG',
        '518880.XSHG',
    ]
    context.params = dict(
        bias_n=60,
        momentum_n=25,
        slope_n=25,
        efficiency_n=25,
        weights=[0.3, 0.3, 0.4],
        switch_ratio=1.5,
        allocation=0.99,
    )
    context.warmup_complete = False

    # 本地 BulletTrade 使用字典，聚宽使用 RunParams 对象。
    run_params = getattr(context, 'run_params', None)
    if isinstance(run_params, dict):
        extras = run_params.get('extras') or {}
    else:
        extras = getattr(run_params, 'extras', None) or {}

    if set(extras) - set(context.params):
        raise ValueError('Unknown research parameter')
    context.params.update(extras)

    p = context.params
    for key in ['bias_n', 'momentum_n', 'slope_n', 'efficiency_n']:
        if type(p[key]) is not int or p[key] < 2:
            raise ValueError('Window parameter must be integer >= 2: ' + key)

    weights = np.asarray(p['weights'], dtype=float)
    if (
        weights.shape != (3,)
        or not np.isfinite(weights).all()
        or (weights < 0).any()
        or not np.isclose(weights.sum(), 1)
    ):
        raise ValueError(
            'Weights parameter must be three nonnegative finite values summing to one'
        )

    if (
        not np.isfinite(p['switch_ratio'])
        or p['switch_ratio'] < 1
        or not np.isfinite(p['allocation'])
        or not 0 < p['allocation'] <= 1
    ):
        raise ValueError('Invalid switch_ratio/allocation parameter')

    set_universe(context.pool)
    set_option('avoid_future_data', True)
    set_slippage(FixedSlippage(0.001))
    set_order_cost(
        OrderCost(
            open_tax=0,
            close_tax=0,
            open_commission=0.0003,
            close_commission=0.0003,
            min_commission=5,
        ),
        type='fund',
    )
    run_daily(rebalance, time='09:30')


def rebalance(context):
    p = context.params
    count = _py.max(
        p['bias_n'] + p['momentum_n'] - 1,
        p['slope_n'],
        p['efficiency_n'],
    )
    factors = {}

    for security in context.pool:
        history = attribute_history(
            security,
            count,
            '1d',
            ['open', 'high', 'low', 'close'],
            skip_paused=False,
            df=True,
            fq='pre',
        )

        ohlc = np.asarray(
            history[['open', 'high', 'low', 'close']].values,
            dtype=float,
        )
        valid_rows = np.all(
            np.isfinite(ohlc) & (ohlc > 0),
            axis=1,
        )
        valid_history = (
            len(history) == count
            and bool(valid_rows.all())
        )

        if not valid_history:
            if getattr(context, 'warmup_complete', False):
                # 完成预热后再遇到异常，输出详细诊断并停止。
                score_history(
                    history, p, context.current_dt.date(), security
                )
                raise ValueError(
                    'ETF3 history lost after warmup: ' + security
                )

            # 预热不足时跳过当天，不填充或删除异常行情。
            log.info(
                'ETF3 warmup pending: security=%s today=%s '
                'rows=%s/%s valid_rows=%s/%s'
                % (
                    security,
                    str(context.current_dt.date()),
                    len(history),
                    count,
                    int(valid_rows.sum()),
                    count,
                )
            )
            return

        factors[security] = score_history(
            history, p, context.current_dt.date(), security
        )

    # 所有 ETF 均通过完整历史窗口校验后，才完成预热。
    if not getattr(context, 'warmup_complete', False):
        log.info(
            'ETF3 warmup complete: today='
            + str(context.current_dt.date())
        )
    context.warmup_complete = True

    scores = combine_factors(factors, p['weights'])
    held = [
        s
        for s in context.pool
        if s in context.portfolio.positions
        and context.portfolio.positions[s].total_amount > 0
    ]
    current = held[0] if held else None
    target = choose_target(scores, current, p['switch_ratio'])

    log.info(
        'ETF3 scores='
        + str(scores)
        + ' current='
        + str(current)
        + ' target='
        + target
    )

    for security in held:
        if security != target:
            order_target(security, 0)

    if _py.any(
        s != target
        and s in context.portfolio.positions
        and context.portfolio.positions[s].total_amount > 0
        for s in held
    ):
        log.info('ETF3 liquidation incomplete; no second ETF purchase')
        return

    if target != current:
        order_target_value(
            target,
            context.portfolio.total_value * p['allocation'],
        )