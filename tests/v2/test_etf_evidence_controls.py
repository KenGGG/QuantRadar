"""Control strategies have explicit allocation and timing conventions."""
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import runpy
import pandas as pd
import pytest

SOURCE = Path(__file__).resolve().parents[2] / 'examples/v2/etf_evidence_baseline.py'

def setup(mode):
    module = runpy.run_path(str(SOURCE))
    fn = module['rebalance']
    fn.__globals__.update(order_target=Mock(), order_target_value=Mock())
    context = SimpleNamespace(current_dt=datetime(2020,1,2,9,30),
        pool=['512890.XSHG','159949.XSHE','513100.XSHG','518880.XSHG'],
        params={'mode':mode,'security':'159949.XSHE','earliest':'2019-05-29'},
        portfolio=SimpleNamespace(positions={},total_value=500000),month=None)
    return fn,context

def test_hold_waits_for_common_start_then_only_buys_once():
    fn,c = setup('hold')
    c.current_dt = datetime(2019,5,28,9,30)
    fn(c)
    fn.__globals__['order_target_value'].assert_not_called()
    c.current_dt = datetime(2019,5,29,9,30)
    fn(c)
    fn.__globals__['order_target_value'].assert_called_once_with('159949.XSHE',495000)
    c.portfolio.positions['159949.XSHE'] = SimpleNamespace(total_amount=100,value=495000)
    fn(c)
    assert fn.__globals__['order_target_value'].call_count == 1

def test_equal_rebalances_once_per_month_and_sells_before_buys():
    fn,c = setup('equal')
    actions = []
    fn.__globals__['order_target_value'] = lambda s,value: actions.append((s,value))
    c.portfolio.positions[c.pool[-1]] = SimpleNamespace(total_amount=100,value=200000)
    fn(c)
    assert actions[0] == (c.pool[-1],123750)
    assert len(actions) == 4
    fn(c)
    assert len(actions) == 4
    c.current_dt = datetime(2020,2,3,9,30)
    fn(c)
    assert len(actions) == 8

def test_momentum_uses_26_prior_closes_for_25_intervals():
    fn,c = setup('momentum')
    def history(s,count,period,fields,**kwargs):
        assert (count,period,fields,kwargs['fq']) == (26,'1d',['close'],'pre')
        return pd.DataFrame({'close':[1]*25+[1+c.pool.index(s)*.1]})
    fn.__globals__['attribute_history'] = history
    fn(c)
    fn.__globals__['order_target_value'].assert_called_once_with('518880.XSHG',495000)

def test_rotation_does_not_buy_when_old_position_not_liquidated():
    fn,c = setup('hold')
    c.portfolio.positions[c.pool[0]] = SimpleNamespace(total_amount=100,value=500000)
    fn(c)
    fn.__globals__['order_target'].assert_called_once_with(c.pool[0],0)
    fn.__globals__['order_target_value'].assert_not_called()

def test_missing_momentum_data_fails_instead_of_filling():
    fn,c = setup('momentum')
    fn.__globals__['attribute_history'] = lambda *a,**k: pd.DataFrame({'close':[1]*25})
    with pytest.raises(ValueError,match='Missing prior-day'):
        fn(c)
