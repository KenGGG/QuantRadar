"""Artificial OHLC fixtures test mathematics, NOT historical backtest data."""
from pathlib import Path
import runpy
import numpy as np
import pandas as pd

SOURCE = Path(__file__).resolve().parents[2] / 'examples/v2/etf_three_factor_article.py'


def strategy():
    return runpy.run_path(str(SOURCE)) if SOURCE.exists() else {}


def test_bias_uses_rolling_mean_and_last_normalized_window():
    fn = strategy().get('bias_factor')
    assert callable(fn), 'bias_factor behavior not implemented'
    assert np.isclose(fn([1, 2, 3, 4], 2, 3), -714.2857142857146)


def test_price_slope_is_scaled_by_regression_r_squared():
    fn = strategy().get('slope_factor')
    assert callable(fn), 'slope_factor behavior not implemented'
    assert np.isclose(fn([2, 4, 6, 8], 4), 10000)
    assert np.isclose(fn([2, 2, 2, 2], 4), 0)
    close = np.array([2, 5, 3, 8], dtype=float)
    y = close / close[0]
    x = np.arange(1, 5)
    slope, intercept = np.polyfit(x, y, 1)
    r2 = 1 - np.sum((y - (slope*x + intercept))**2) / np.sum((y-y.mean())**2)
    assert np.isclose(fn(close, 4), 10000*slope*r2)


def test_efficiency_uses_ohlc_pivot_log_path_with_zero_volatility():
    fn = strategy().get('efficiency_factor')
    assert callable(fn), 'efficiency_factor behavior not implemented'
    frame = pd.DataFrame({k: [1., 2., 1., 4.] for k in ['open','high','low','close']})
    assert np.isclose(fn(frame, 4), 100*np.log(4)*0.5)
    frame.loc[:, :] = 3.
    assert fn(frame, 4) == 0
    down = pd.DataFrame({k: [4., 2., 1.] for k in frame.columns})
    assert np.isclose(fn(down, 3), -100*np.log(4))


def test_scores_cross_sectional_population_zscore_and_constant_factor():
    fn = strategy().get('combine_factors')
    assert callable(fn), 'combine_factors behavior not implemented'
    scores = fn({'a': [1, 4, 7], 'b': [3, 2, 7]}, [0.3, 0.3, 0.4])
    assert np.isclose(scores['a'], 0)
    assert np.isclose(scores['b'], 0)
    scores = fn({'a': [1, 1, 1], 'b': [3, 3, 3]}, [0.3, 0.3, 0.4])
    assert np.isclose(scores['a'], -1)
    assert np.isclose(scores['b'], 1)


def test_selection_literal_strict_multiplier_retains_ties_and_negative_paradox():
    fn = strategy().get('choose_target')
    assert callable(fn), 'choose_target behavior not implemented'
    assert fn({'a': 1, 'b': 1.5}, 'a', 1.5) == 'a'
    assert fn({'a': 1, 'b': 1.5001}, 'a', 1.5) == 'b'
    assert fn({'a': -1, 'b': -0.999}, 'a', 1.5) == 'b'
    assert fn({'a': 0, 'b': 0}, 'b', 1.5) == 'b'
    assert fn({'a': 0, 'b': 0}, None, 1.5) == 'a'
    assert fn({'a': 2, 'b': 1}, 'a', 1.5) == 'a'


def test_history_requires_full_warmup_prior_day_and_positive_finite_ohlc():
    fn = strategy().get('score_history')
    assert callable(fn), 'score_history behavior not implemented'
    import pytest
    frame = pd.DataFrame({k: np.arange(1., 8.) for k in ['open','high','low','close']}, index=pd.bdate_range('2025-01-01', periods=7))
    params = dict(bias_n=4, momentum_n=4, slope_n=4, efficiency_n=4)
    cutoff = pd.Timestamp('2025-01-10').date()
    scores = fn(frame, params, cutoff)
    assert len(scores) == 3 and np.isfinite(scores).all()
    with pytest.raises(ValueError, match='warmup'):
        fn(frame.iloc[1:], params, cutoff)
    with pytest.raises(ValueError, match='prior'):
        fn(frame, params, frame.index[-1].date())
    bad = frame.copy(); bad.iloc[0, 0] = 0
    with pytest.raises(ValueError, match='positive finite'):
        fn(bad, params, cutoff)
    bad.iloc[0, 0] = np.nan
    with pytest.raises(ValueError, match='positive finite'):
        fn(bad, params, cutoff)


def test_initialize_applies_explicit_daily_research_defaults_and_extras():
    from types import SimpleNamespace
    ns = strategy()
    fn = ns.get('initialize')
    assert callable(fn), 'initialize behavior not implemented'
    calls = []
    for name in ['set_universe','set_option','set_slippage','set_order_cost','run_daily']:
        fn.__globals__[name] = lambda *args, _name=name, **kwargs: calls.append((_name, args, kwargs))
    fn.__globals__['FixedSlippage'] = lambda value: value
    fn.__globals__['OrderCost'] = lambda **kwargs: kwargs
    context = SimpleNamespace(run_params={'extras': {'bias_n': 30}})
    fn(context)
    assert context.pool == ['512890.XSHG','159949.XSHE','513100.XSHG','518880.XSHG']
    assert context.params['bias_n'] == 30
    assert context.params['momentum_n'] == 25
    assert context.params['weights'] == [0.3, 0.3, 0.4]
    assert context.params['allocation'] == 0.99
    assert ('set_option', ('avoid_future_data', True), {}) in calls
    assert ('set_slippage', (0.001,), {}) in calls
    cost = next(c for c in calls if c[0] == 'set_order_cost')
    assert cost[1][0]['open_commission'] == 0.0003 and cost[2] == {'type': 'fund'}
    assert next(c for c in calls if c[0] == 'run_daily')[2] == {'time': '09:30'}


def test_rebalance_scores_real_helpers_and_sells_before_single_target_buy():
    from types import SimpleNamespace as NS
    fn = strategy().get('rebalance')
    assert callable(fn), 'rebalance behavior not implemented'
    params = dict(bias_n=2, momentum_n=3, slope_n=3, efficiency_n=3, weights=[0.3,0.3,0.4], switch_ratio=1.5, allocation=0.99)
    frames = {s: pd.DataFrame({k: values for k in ['open','high','low','close']}, index=pd.bdate_range('2025-01-01', periods=4)) for s, values in {'a':[4.,3.,2.,1.], 'b':[1.,2.,3.,4.]}.items()}
    ctx = NS(pool=['a','b'], params=params, current_dt=pd.Timestamp('2025-01-07 09:30'), portfolio=NS(total_value=500000, positions={'a': NS(total_amount=100)}))
    calls = []
    def history(security, count, unit, fields, **kwargs):
        assert (count, unit, fields, kwargs) == (4, '1d', ['open','high','low','close'], {'skip_paused':False, 'df':True, 'fq':'pre'})
        return frames[security]
    def sell(security, amount):
        calls.append(('sell',security,amount)); ctx.portfolio.positions[security].total_amount = 0
    fn.__globals__.update(attribute_history=history, order_target=sell, order_target_value=lambda s,v: calls.append(('buy',s,v)), log=NS(info=lambda text: None))
    fn(ctx)
    assert calls == [('sell','a',0), ('buy','b',495000)]


def test_rebalance_keeps_cash_during_initial_incomplete_pool_warmup():
    from types import SimpleNamespace as NS
    fn = strategy()['rebalance']
    params = dict(bias_n=60, momentum_n=25, slope_n=25, efficiency_n=25)
    ctx = NS(pool=['a'], params=params, current_dt=pd.Timestamp('2019-01-02 09:30'))
    messages = []
    fn.__globals__.update(attribute_history=lambda *args, **kwargs: pd.DataFrame(), log=NS(info=messages.append))
    fn(ctx)
    assert len(messages) == 1 and 'warmup' in messages[0]


def test_initialize_rejects_invalid_or_unknown_research_parameters_before_api_calls():
    import pytest
    from types import SimpleNamespace as NS
    for extras in [{'bias_n': 0}, {'momentum_n': 1}, {'slope_n': 2.5}, {'efficiency_n': True}, {'weights':[1,2]}, {'weights':[0.3,0.3,float('nan')]}, {'weights':[-1,1,1]}, {'allocation':1.1}, {'switch_ratio':0.5}, {'typo':3}]:
        fn = strategy()['initialize']
        calls = []
        for name in ['set_option','set_slippage','set_order_cost','run_daily']:
            fn.__globals__[name] = lambda *args, **kwargs: None
        fn.__globals__['FixedSlippage'] = lambda value: value
        fn.__globals__['OrderCost'] = lambda **kwargs: kwargs
        fn.__globals__['set_universe'] = lambda *args: calls.append(args)
        with pytest.raises(ValueError, match='parameter'):
            fn(NS(run_params={'extras':extras}))
        assert not calls


def test_failed_liquidation_never_buys_second_etf():
    from types import SimpleNamespace as NS
    fn = strategy()['rebalance']
    p = dict(bias_n=2,momentum_n=3,slope_n=3,efficiency_n=3,weights=[0.3,0.3,0.4],switch_ratio=1.5,allocation=0.99)
    frames = {s: pd.DataFrame({k: values for k in ['open','high','low','close']}, index=pd.bdate_range('2025-01-01',periods=4)) for s,values in {'a':[4.,3.,2.,1.],'b':[1.,2.,3.,4.]}.items()}
    ctx = NS(pool=['a','b'],params=p,current_dt=pd.Timestamp('2025-01-07'),portfolio=NS(total_value=500000,positions={'a':NS(total_amount=100)}))
    buys = []
    fn.__globals__.update(attribute_history=lambda s,*args,**kwargs: frames[s],order_target=lambda *args: None,order_target_value=lambda *args: buys.append(args),log=NS(info=lambda text: None))
    fn(ctx)
    assert buys == []


def test_incomplete_history_after_warmup_is_error_not_silent_stale_holding():
    import pytest
    from types import SimpleNamespace as NS
    fn = strategy()['rebalance']
    ctx = NS(pool=['a'], params=dict(bias_n=2,momentum_n=3,slope_n=3,efficiency_n=3), current_dt=pd.Timestamp('2025-01-07'), warmup_complete=True)
    fn.__globals__.update(attribute_history=lambda *args, **kwargs: pd.DataFrame(), log=NS(info=lambda text: None))
    with pytest.raises(ValueError, match='history lost'):
        fn(ctx)
