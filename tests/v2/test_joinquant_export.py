import importlib.util
from pathlib import Path
from types import SimpleNamespace
import io
import pandas as pd

def test_export_has_full_windows_one_header_and_no_orders():
    path=Path(__file__).resolve().parents[2]/'examples/v2/etf_three_factor_joinquant_diagnostic.py'
    spec=importlib.util.spec_from_file_location('jq_export',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    fields=['open','high','low','close','volume','factor']
    history=pd.DataFrame({k:[1.0]*84 for k in fields},index=pd.bdate_range(end='2019-10-10',periods=84))
    m.attribute_history=lambda *args,**kwargs:history.copy()
    m.get_price=lambda *args,**kwargs:history.tail(1).copy()
    saved=[]
    m.write_file=lambda filename,content,append:saved.append((filename,content,append))
    m.log=SimpleNamespace(info=lambda *args:None)
    def unexpected(*args,**kwargs):raise AssertionError('export placed an order')
    m.order_target=m.order_target_value=unexpected
    c=SimpleNamespace(current_dt=pd.Timestamp('2019-10-11 15:30'),
        params=dict(bias_n=60,momentum_n=25,slope_n=25,efficiency_n=25),
        pool=['512890.XSHG','159949.XSHE','513100.XSHG','518880.XSHG'])
    m.export_alignment_data(c)
    assert saved[0][2] is False
    frame=pd.read_csv(io.StringIO(saved[0][1]))
    assert len(frame)==340 and set(frame['view'])=={'history','current'}
    assert all(k in frame.columns for k in fields)
    c.current_dt=pd.Timestamp('2021-02-26 15:30');m.export_alignment_data(c)
    assert saved[1][2] is True and not saved[1][1].startswith('bar_date,')
    c.current_dt=pd.Timestamp('2021-02-25 15:30');m.export_alignment_data(c)
    assert len(saved)==2

def test_daily_equity_export_keeps_prior_day_benchmark_base():
    path=Path(__file__).resolve().parents[2]/'examples/v2/etf_three_factor_joinquant_diagnostic.py'
    spec=importlib.util.spec_from_file_location('jq_daily_export',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    m.get_price=lambda *args,**kwargs:pd.DataFrame({'close':[3.0 if 'count' in kwargs else 3.3]})
    saved=[];m.write_file=lambda filename,content,append:saved.append((filename,content,append))
    portfolio=SimpleNamespace(total_value=500000,available_cash=500000,positions_value=0,starting_cash=500000)
    c=SimpleNamespace(current_dt=pd.Timestamp('2019-01-02 15:30'),previous_date=pd.Timestamp('2018-12-28'),portfolio=portfolio)
    m.export_alignment_daily(c)
    row=pd.read_csv(io.StringIO(saved[0][1])).iloc[0]
    assert saved[0][0]=='quantradar_daily_equity.csv' and saved[0][2] is False
    assert abs(row.benchmark_returns_pct-10)<1e-10 and row.returns_pct==0
    c.current_dt=pd.Timestamp('2019-01-03 15:30');c.previous_date=pd.Timestamp('2019-01-02')
    m.export_alignment_daily(c)
    assert c._alignment_benchmark_base==3.0 and saved[1][2] is True
