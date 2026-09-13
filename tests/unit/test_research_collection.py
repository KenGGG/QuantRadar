import json
import pytest
from quantradar.datahub import research_collection as rc

class Response:
    status_code=200;headers={};content=b'{"data": [1]}'
    def iter_content(self,chunk_size):yield self.content
    def close(self):pass
    def raise_for_status(self):
        if self.status_code>=400:
            import requests
            raise requests.HTTPError(f'{self.status_code}',response=self)
class Session:
    def __init__(self):self.calls=[];self.response=Response()
    def request(self,method,url,**kwargs):self.calls.append((method,url,kwargs));return self.response


def test_same_request_reuses_raw_across_instances_and_verifies_hash(tmp_path):
    s=Session(); client=rc.GovernedHttpSource(tmp_path,'eastmoney-etf',session=s,interval_seconds=0)
    one=client.fetch('https://push2his.eastmoney.com/api/qt/stock/kline/get',{'secid':'1.510300'},contract='etf-raw-v1')
    two=rc.GovernedHttpSource(tmp_path,'eastmoney-etf',session=s,interval_seconds=0).fetch('https://push2his.eastmoney.com/api/qt/stock/kline/get',{'secid':'1.510300'},contract='etf-raw-v1')
    assert one['content']==two['content']==b'{"data": [1]}'
    assert two['cache_hit'] is True and len(s.calls)==1
    assert one['evidence_level']=='HTTP_RAW'
    (tmp_path/'raw-artifacts/raw'/one['raw_sha256']).write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='hash'):
        client.fetch('https://push2his.eastmoney.com/api/qt/stock/kline/get',{'secid':'1.510300'},contract='etf-raw-v1')


def test_http_error_preserves_bytes_and_blocks_following_calls(tmp_path):
    s=Session();s.response.status_code=429;s.response.content=b'limited';s.response.headers={'Retry-After':'600'}
    client=rc.GovernedHttpSource(tmp_path,'eastmoney-etf',session=s,interval_seconds=0)
    with pytest.raises(Exception,match='429'):
        client.fetch('https://push2his.eastmoney.com/api/qt/stock/kline/get',{},contract='v1')
    records=list((tmp_path/'journals').glob('*.json'));assert records
    journal=json.loads(records[0].read_text());unit=next(iter(journal['units'].values()))
    assert unit['status']=='FAILED' and unit['http_status']==429 and unit['raw_sha256']
    with pytest.raises(Exception,match='cooldown|circuit'):
        client.fetch('https://push2his.eastmoney.com/api/qt/stock/kline/get',{'other':'1'},contract='v1')
    assert len(s.calls)==1


def test_oversize_response_and_unknown_endpoint_refused(tmp_path):
    s=Session();c=rc.GovernedHttpSource(tmp_path,'eastmoney-etf',session=s,interval_seconds=0,max_bytes=3)
    with pytest.raises(ValueError,match='size'):
        c.fetch('https://push2his.eastmoney.com/api/qt/stock/kline/get',{},contract='v1')
    with pytest.raises(ValueError,match='endpoint'):
        c.fetch('https://unapproved.invalid/private',{},contract='v1')


def test_official_etf_evidence_pdf_paths_are_allowlisted(tmp_path):
    session = Session()
    sse = rc.GovernedHttpSource(tmp_path, 'sse-etf-evidence', session=session, interval_seconds=0)
    receipt = sse.fetch('https://www.sse.com.cn/disclosure/fund/announcement/c/new/2023-03-31/510300_20230331_G1XG.pdf', {}, contract='sse-etf-pdf-v1')
    assert receipt['content'] == b'{"data": [1]}'
    szse = rc.GovernedHttpSource(tmp_path, 'szse-etf-evidence', session=session, interval_seconds=0)
    szse.fetch('https://disc.static.szse.cn/download/disc/disk03/finalpage/2025-08-29/0795f2c9-30a3-4825-bf25-37f08ddfe16a.PDF', {}, contract='szse-etf-pdf-v1')
    with pytest.raises(ValueError, match='unapproved'):
        sse.fetch('https://www.sse.com.cn/disclosure/fund/announcement/c/new/2023-03-31/not-a-pdf.html', {}, contract='sse-etf-pdf-v1')


def test_jsfund_etf_evidence_requires_product_announcement_pdf_path(tmp_path):
    source = rc.GovernedHttpSource(tmp_path, 'jsfund-etf-evidence', session=Session(), interval_seconds=0)
    source.fetch('https://www.jsfund.cn/plat_files/upload/product_ann/20250314/202503141741951225663/dividend.pdf', {}, contract='jsfund-etf-pdf-v1')
    with pytest.raises(ValueError, match='unapproved'):
        source.fetch('https://www.jsfund.cn/plat_files/upload/product_ann/20250314/dividend.html', {}, contract='jsfund-etf-pdf-v1')
