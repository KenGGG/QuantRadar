import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd


def strategy():
    path=Path(__file__).resolve().parents[2]/'examples/v2/etf_three_factor_joinquant_fixed.py'
    spec=importlib.util.spec_from_file_location('jq_fixed',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Reproduce the problematic global namespace without relying on JQ access.
    module.any=np.any
    module.max=np.max
    module.log=SimpleNamespace(info=lambda *args:None)
    pool=['512890.XSHG','159949.XSHE','513100.XSHG','518880.XSHG']
    params=dict(bias_n=60,momentum_n=25,slope_n=25,efficiency_n=25,
                weights=[.3,.3,.4],switch_ratio=1.5,allocation=.99)
    context=SimpleNamespace(pool=pool,params=params,warmup_complete=False,
        current_dt=pd.Timestamp('2024-06-03 09:30'),
        portfolio=SimpleNamespace(positions={},total_value=500000))
    history=pd.DataFrame({k:np.linspace(1,2,84) for k in ['open','high','low','close']},
                         index=pd.bdate_range(end='2024-05-31',periods=84))
    module.attribute_history=lambda *args,**kwargs:history.copy()
    module.combine_factors=lambda *args:{code:float(i) for i,code in enumerate(pool)}
    orders=[]
    module.order_target=lambda code,amount:orders.append(('sell',code,amount))
    module.order_target_value=lambda code,value:orders.append(('buy',code,value))
    return module,context,orders,history


def test_empty_portfolio_buys_under_numpy_shadowing():
    module,context,orders,_=strategy()
    module.rebalance(context)
    assert context.warmup_complete
    assert orders==[('buy','518880.XSHG',495000)]


def test_unfinished_liquidation_still_blocks_buying():
    module,context,orders,_=strategy()
    context.portfolio.positions['512890.XSHG']=SimpleNamespace(total_amount=100)
    module.rebalance(context)
    assert orders==[('sell','512890.XSHG',0)]


def test_completed_liquidation_allows_switch():
    module,context,orders,_=strategy()
    context.portfolio.positions['512890.XSHG']=SimpleNamespace(total_amount=100)
    def sell(code,amount):
        orders.append(('sell',code,amount))
        context.portfolio.positions[code].total_amount=0
    module.order_target=sell
    module.rebalance(context)
    assert orders==[('sell','512890.XSHG',0),('buy','518880.XSHG',495000)]


def test_future_bar_guard_and_tie_rule_preserved():
    import pytest
    module,context,_,history=strategy()
    history.index=list(history.index[:-1])+[context.current_dt.normalize()]
    with pytest.raises(ValueError,match='prior-day'):
        module.score_history(history,context.params,context.current_dt.date())
    assert module.choose_target({'A':1,'B':1},'B',1.5)=='B'
