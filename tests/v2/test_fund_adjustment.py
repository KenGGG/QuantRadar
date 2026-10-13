from unittest.mock import Mock
import numpy as np
import pandas as pd
import pytest
from quantradar2.provider import ResearchQmtProvider, RemoteQmtProvider


def source(monkeypatch):
    provider=object.__new__(ResearchQmtProvider)
    provider.get_security_info=Mock(return_value={'type':'fund','start_date':'2019-01-01'})
    provider.get_split_dividend=Mock(return_value=[{'date':'2021-10-25','scale_factor':2}])
    raw=pd.DataFrame({'open':[1.144,1.63,.87], 'close':[1.15,1.639,.801],
                      'volume':[1723500,3280100,4935000], 'pre_close':[1.14,1.62,.801]},
                      index=pd.to_datetime(['2019-10-11','2021-10-21','2021-10-25']))
    def fetch(self,security,**kwargs):
        assert kwargs['fq']=='none'
        frame=raw
        if kwargs.get('start_date'):frame=frame.loc[frame.index>=pd.Timestamp(kwargs['start_date'])]
        if kwargs.get('end_date'):frame=frame.loc[frame.index<=pd.Timestamp(kwargs['end_date'])]
        if kwargs.get('count'):frame=frame.tail(kwargs['count'])
        return frame[kwargs['fields']].copy()
    monkeypatch.setattr(RemoteQmtProvider,'get_price',fetch)
    return provider,raw


def test_exchange_reference_and_six_decimal_factor_match_export(monkeypatch):
    p,raw=source(monkeypatch)
    actual=p.get_price('512890.XSHG',start_date='2019-10-11',end_date='2021-10-25',
                      fields=['open','close','volume'],fq='pre',pre_factor_ref_date='2026-10-12')
    assert actual.iloc[0]['open']==.559
    assert actual.iloc[0]['close']==.562
    assert actual.iloc[0]['volume']==3526612
    assert actual.iloc[1]['close']==actual.iloc[2]['close']==.801
    facts=p._fund_adjustment_cache[('512890.XSHG','2026-10-12')][0]
    assert facts['post_factor']==2.046192
    assert facts['multiplier']==pytest.approx(.4887126916731176)
    window=p.get_price('512890.XSHG',end_date='2019-10-11',count=1,
                       fields=['open','close','volume'],fq='pre',pre_factor_ref_date='2026-10-12')
    pd.testing.assert_frame_equal(window,actual.iloc[:1])
    p.get_split_dividend.assert_called_once()
    assert raw.iloc[0]['close']==1.15


def test_anchor_before_action_uses_inverse_factor(monkeypatch):
    p,_=source(monkeypatch)
    actual=p.get_price('512890.XSHG',start_date='2021-10-25',end_date='2021-10-25',
                       fields=['close'],fq='pre',pre_factor_ref_date='2019-10-11')
    assert actual.iloc[0]['close']==1.639


def test_missing_exchange_reference_fails_without_theoretical_fallback(monkeypatch):
    p,_=source(monkeypatch)
    monkeypatch.setattr(RemoteQmtProvider,'get_price',lambda *a,**kw:pd.DataFrame())
    with pytest.raises(ValueError,match='reference missing'):
        p.get_price('512890.XSHG',fields=['close'],fq='pre')
