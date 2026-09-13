import pytest
import pandas as pd
from quantradar.datahub.adapters import BaostockAdapter
from quantradar.datahub.sources import normalize_baostock_daily_bundle


def test_baostock_terminal_error_rejects_partial_result():
    class Result:
        error_code='0'; error_msg=''; fields=['date']
        calls=0
        def next(self):
            self.calls+=1
            if self.calls==1:return True
            self.error_code='10001011';self.error_msg='connection lost';return False
        def get_row_data(self):return ['2020-01-02']
    with pytest.raises(RuntimeError,match='10001011'):
        BaostockAdapter._rows(Result())


def test_baostock_row_width_mismatch_rejected():
    class Result:
        error_code='0';error_msg='';fields=['date','close'];calls=0
        def next(self):self.calls+=1;return self.calls==1
        def get_row_data(self):return ['2020-01-02']
    with pytest.raises(ValueError,match='width'):
        BaostockAdapter._rows(Result())


def test_missing_state_is_preserved_unknown_and_fractional_state_rejected():
    args=dict(raw_sha256='a'*64,fetched_at='now',adapter_version='test')
    row=dict(date='2020-01-02',code='sh.600000',tradestatus='',isST=None)
    r=normalize_baostock_daily_bundle([row],**args)
    assert r['trade_status'][0]['tradestatus'] is None
    assert r['trade_status'][0]['is_st'] is None
    for bad in ['0.5','2','inf']:
        with pytest.raises(ValueError):normalize_baostock_daily_bundle([{**row,'isST':bad}],**args)


def test_baostock_b_shares_rejected_by_stock_bundle():
    with pytest.raises(ValueError,match='A.share'):
        normalize_baostock_daily_bundle([dict(date='2020-01-02',code='sh.900901',tradestatus='1',isST='0')],raw_sha256='a'*64,fetched_at='now',adapter_version='test')


def test_standard_panel_units_and_vwap_zero_quantity():
    from quantradar.datahub.research_inputs import standard_panel
    raw=pd.DataFrame(dict(open=[10,10],high=[12,12],low=[9,9],close=[11,11],volume=[2,0],amount=[2.2,0],adjclose=[22,22]))
    result=standard_panel(raw,unit_contract='base-hands-thousand-yuan',adjustment='raw')
    assert result.loc[0,'volume_shares']==200
    assert result.loc[0,'amount_cny']==2200
    assert result.loc[0,'vwap']==11
    assert pd.isna(result.loc[1,'vwap'])
    assert result.loc[1,'vwap_missing_reason']=='ZERO_VOLUME'
    native=raw.assign(volume=[200,0],amount=[2200,0])
    assert standard_panel(native,unit_contract='baostock-shares-yuan',adjustment='raw').loc[0,'vwap']==11


def test_adjustment_scales_all_research_prices_but_not_quantity_and_rejects_missing():
    from quantradar.datahub.research_inputs import standard_panel
    raw=pd.DataFrame(dict(open=[10,11],high=[12,13],low=[9,10],close=[11,12],volume=[200,200],amount=[2200,2400],adjclose=[22,36]))
    r=standard_panel(raw,unit_contract='baostock-shares-yuan',adjustment='fixed_hfq')
    assert r.loc[0,'open']==20 and r.loc[0,'vwap']==22 and r.loc[1,'close']==36
    assert r.loc[0,'raw_open']==10 and r.loc[0,'volume_shares']==200
    assert r.attrs['strict_pit_ready'] is False
    with pytest.raises(ValueError,match='factor'):
        standard_panel(raw.assign(adjclose=float('nan')),unit_contract='baostock-shares-yuan',adjustment='fixed_hfq')
    with pytest.raises(ValueError,match='unit'):
        standard_panel(raw,unit_contract='guess',adjustment='raw')


def test_extended_daily_bundle_preserves_one_receipt_and_separate_domains(monkeypatch):
    from contextlib import contextmanager
    seen=[]
    class Result:
        error_code='0';error_msg='';fields=['date','code','open','high','low','close','preclose','volume','amount','tradestatus','isST'];calls=0
        def next(self):self.calls+=1;return self.calls==1
        def get_row_data(self):return ['2020-01-02','sh.600000','10','11','9','10','9.8','100','1000','1','0']
    class Client:
        def query_history_k_data_plus(self,code,fields,**kwargs):seen.append(fields);return Result()
    adapter=BaostockAdapter()
    @contextmanager
    def session():yield Client()
    monkeypatch.setattr(adapter,'_session',session)
    _,fetched=next(adapter.daily_bundles(['600000.SH'],'2020-01-02','2020-01-02',extended=True))
    assert 'preclose' in seen[0]
    assert fetched.evidence_level=='SDK_RESPONSE_SNAPSHOT'
    assert fetched.candidate_domains['price'][0]['preclose']==9.8
    assert fetched.rows==fetched.candidate_domains['trade_status']
    assert fetched.candidate_domains['price'][0]['raw_sha256']==fetched.rows[0]['raw_sha256']


def test_terminal_failure_attaches_partial_sdk_evidence():
    from quantradar.datahub.adapters import SourceResponseError
    class Result:
        error_code='0';error_msg='';fields=['date'];calls=0
        def next(self):
            self.calls+=1
            if self.calls==1:return True
            self.error_code='10001011';self.error_msg='lost';return False
        def get_row_data(self):return ['2020-01-02']
    with pytest.raises(SourceResponseError) as error:BaostockAdapter._rows(Result())
    assert b'2020-01-02' in error.value.raw_bytes and b'10001011' in error.value.raw_bytes
