import pytest
from quantradar.datahub import fund_adapters as fa


def test_fund_pages_are_parsed_as_literals_without_execution(tmp_path):
    payload=b'var jjfh_jjjs=[2,2,3];var jjfh_data=[["510300","ETF","2020-01-02","2020-01-03","0.12","2020-01-06",""]];var jjfh_jjgs=1;'
    page=fa.parse_fund_event_page(payload,kind='dividend',year=2020,page=1)
    assert page['page_count']==2
    assert page['rows'][0]['cash_per_unit']==.12
    assert page['rows'][0]['pay_date']=='2020-01-06'
    assert page['rows'][0]['share_multiplier'] is None
    assert page['rows'][0]['qualification']=='ANNOUNCEMENT_UNVERIFIED'
    malicious=b'var jjfh_jjjs=[1,1,1];var jjfh_data=__import__("os").system("false");var jjfh_jjgs=1;'
    with pytest.raises(ValueError):fa.parse_fund_event_page(malicious,kind='dividend',year=2020,page=1)


def test_event_empty_and_missing_metadata_are_distinct():
    empty=b'var jjcf_jjjs=[0,0,0];var jjcf_data=[];var jjcf_jjgs=0;'
    assert fa.parse_fund_event_page(empty,kind='split',year=2020,page=1)['rows']==[]
    with pytest.raises(ValueError):fa.parse_fund_event_page(b'error',kind='split',year=2020,page=1)
    split=b'var jjcf_jjjs=[1,1,1];var jjcf_data=[["510300","ETF","2020-01-03","split","2",""]];var jjcf_jjgs=1;'
    r=fa.parse_fund_event_page(split,kind='split',year=2020,page=1)['rows'][0]
    assert r['source_split_value']==2 and r['share_multiplier'] is None


def test_daily_units_not_guessed_and_schema_not_coerced():
    data={'rc':0,'data':{'code':'510300','market':1,'klines':['2020-01-02,4,4.1,4.2,3.9,100,41000,0,0,0,0']}}
    r=fa.parse_etf_daily(data,symbol='510300.SH',start='2020-01-01',end='2020-01-03')
    assert r[0]['volume_source']==100 and r[0]['volume_units'] is None
    assert r[0]['amount_source']==41000 and r[0]['unit_status']=='UNIT_UNVERIFIED'
    data['data']['klines']=['2020-01-02,4,4.1,4.2,3.9,bad,41000,0,0,0,0']
    with pytest.raises(ValueError):fa.parse_etf_daily(data,symbol='510300.SH',start='2020-01-01',end='2020-01-03')


def test_no_data_is_not_no_trading_and_duplicates_are_rejected():
    with pytest.raises(ValueError,match='empty'):
        fa.parse_etf_daily({'rc':0,'data':None},symbol='510300.SH',start='2020-01-01',end='2020-01-03')
    line='2020-01-02,4,4.1,4.2,3.9,100,41000,0,0,0,0'
    with pytest.raises(ValueError,match='duplicate'):
        fa.parse_etf_daily({'rc':0,'data':{'code':'510300','market':1,'klines':[line,line]}},symbol='510300.SH',start='2020-01-01',end='2020-01-03')


def test_etf_daily_unit_qualification_normalizes_hands_and_yuan():
    rows = [{
        'symbol': '510300.SH', 'trade_date': '2024-01-02', 'close': 3.45,
        'volume_source': 100.0, 'amount_source': 34500.0,
        'unit_status': 'UNIT_UNVERIFIED',
    }]
    qualified = fa.qualify_etf_daily_units(rows)
    assert qualified[0]['volume_shares'] == 10000.0
    assert qualified[0]['amount_cny'] == 34500.0
    assert qualified[0]['unit_status'] == 'HAND_AND_CNY_QUALIFIED'


def test_etf_unit_qualification_allows_amount_weighted_price_not_close():
    rows = [{
        'symbol': '510300.SH', 'trade_date': '2015-06-30', 'close': 4.484,
        'volume_source': 27653176.0, 'amount_source': 11729333504.0,
        'unit_status': 'UNIT_UNVERIFIED',
    }]
    assert fa.qualify_etf_daily_units(rows)[0]['volume_units'] == 'HAND'
