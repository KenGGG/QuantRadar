"""Governed, content-addressed HTTP receipts for scoped research adapters.

Uses DataHub's existing journal/raw/governor. Receipt completion means bytes were
captured, not that a dataset passed its parser, units, coverage or publication.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
from pathlib import Path
from typing import Any

import requests

from .governor import RequestGovernor, _atomic_json
from .store import RawStore, UpdateJournal

ALLOWED_ENDPOINTS = {
    'eastmoney-etf': {'https://push2his.eastmoney.com/api/qt/stock/kline/get'},
    'eastmoney-fund-events': {'https://fund.eastmoney.com/Data/funddataIndex_Interface.aspx'},
    'eastmoney-fund-announcements': {'https://api.fund.eastmoney.com/f10/JJGG'},
    'eastmoney-fund-profile': {'https://fundf10.eastmoney.com/'},
    'sse-etf-evidence': {'https://www.sse.com.cn/'},
    'szse-etf-evidence': {'https://disc.static.szse.cn/'},
    'cninfo-etf-evidence': {'https://static.cninfo.com.cn/'},
    'chinaamc-etf-evidence': {'https://www.chinaamc.com/'},
    'southernfund-etf-evidence': {'https://www.southernfund.com/'},
    'eastmoney-fund-nav': {'https://api.fund.eastmoney.com/f10/lsjz'},
    'cninfo-dividend': {'https://webapi.cninfo.com.cn/api/sysapi/p_sysapi1139'},
    'sina-etf': {'https://finance.sina.com.cn/realstock/company/'},
}


class GovernedHttpSource:
    def __init__(self, root: Path | str, endpoint: str, *, session=None,
                 interval_seconds: float = 3.0, max_bytes: int = 16_000_000) -> None:
        if endpoint not in ALLOWED_ENDPOINTS:
            raise ValueError('unapproved endpoint contract')
        self.root=Path(root);self.endpoint=endpoint
        self.session=session or requests.Session()
        self.governor=RequestGovernor(self.root/'governance',endpoint,interval_seconds=interval_seconds)
        self.raw=RawStore(self.root/'raw-artifacts')
        self.journal_path=self.root/'journals'/f'research-transport-{endpoint}.json'
        self.max_bytes=max_bytes

    def fetch(self,url: str,params: dict[str, Any],*,contract: str,method: str='GET',headers=None) -> dict:
        allowed=url in ALLOWED_ENDPOINTS[self.endpoint]
        # Sina's official per-symbol static history has a path parameter.
        if self.endpoint=='sina-etf':
            import re
            allowed=bool(re.fullmatch(r'https://finance\.sina\.com\.cn/realstock/company/(sh|sz)\d{6}/hisdata/klc_kl\.js',url))
        if self.endpoint=='eastmoney-fund-profile':
            import re
            allowed=bool(re.fullmatch(r'https://fundf10\.eastmoney\.com/jbgk_\d{6}\.html',url))
        if self.endpoint=='sse-etf-evidence':
            import re
            allowed=bool(re.fullmatch(r'https://www\.sse\.com\.cn/disclosure/fund/announcement/c/(?:new/)?\d{4}-\d{2}-\d{2}/\d{6}_[A-Za-z0-9_]+\.pdf',url))
        if self.endpoint=='szse-etf-evidence':
            import re
            allowed=bool(re.fullmatch(r'https://disc\.static\.szse\.cn/download/disc/disk03/finalpage/\d{4}-\d{2}-\d{2}/[0-9a-f-]+\.PDF',url))
        if self.endpoint=='cninfo-etf-evidence':
            import re
            allowed=bool(re.fullmatch(r'https://static\.cninfo\.com\.cn/finalpage/\d{4}-\d{2}-\d{2}/\d+\.PDF',url))
        if self.endpoint=='chinaamc-etf-evidence':
            import re
            allowed=bool(re.fullmatch(r'https://www\.chinaamc\.com/upload/resources/file/\d{4}/\d{2}/\d{2}/\d+\.pdf',url))
        if self.endpoint=='southernfund-etf-evidence':
            allowed=url == 'https://www.southernfund.com/nfwebApi/DownLoader.java'
        if not allowed or method not in {'GET','POST'} or not contract:
            raise ValueError('unapproved endpoint/method/contract')
        identity={'endpoint':self.endpoint,'url':url,'method':method,'params':params,'contract':contract}
        key=hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        with self.governor.operation_lock():
            journal=UpdateJournal(self.journal_path)
            if not journal.data.get('operation_id'):
                journal.start(f'research-transport-{self.endpoint}',dataset='HTTP_RECEIPTS')
            previous=journal.data['units'].get(key,{})
            if previous.get('status')=='COMPLETE':
                content=self.raw.read(previous['raw_sha256'])
                return {**previous,'content':content,'cache_hit':True,'request_key':key}
            journal.running(key)
            captured={}
            def request():
                response=self.session.request(method,url,params=params,headers=headers or {'User-Agent':'QuantRadar DataHub/2'},timeout=(10,30),stream=True,allow_redirects=False)
                try:
                    chunks=[];size=0
                    for chunk in response.iter_content(chunk_size=65536):
                        size+=len(chunk)
                        if size>self.max_bytes:raise ValueError('response exceeds size limit')
                        chunks.append(chunk)
                    content=b''.join(chunks)
                    receipt=self.raw.put(f'{self.endpoint}/{key}',content)
                    captured.update(raw_sha256=receipt['sha256'],http_status=response.status_code,
                                    response_headers={k:response.headers[k] for k in ('Content-Type','Retry-After','ETag','Last-Modified') if k in response.headers})
                    response.raise_for_status()
                    if response.status_code!=200:raise ValueError(f'unexpected HTTP status {response.status_code}')
                    return content
                finally:response.close()
            try:
                content=self.governor.call(key,request,max_attempts=1)
            except Exception as exc:
                journal.fail(key,f'{type(exc).__name__}: {exc}',**identity,**captured,evidence_level='HTTP_RAW' if captured.get('raw_sha256') else 'NO_RESPONSE')
                # Preserve source Retry-After beyond the existing minimum cooldown.
                retry=captured.get('response_headers',{}).get('Retry-After')
                if captured.get('http_status') in (401,403,429) or retry:
                    ledger=self.governor.status();now=datetime.now(timezone.utc)
                    deadline=now+timedelta(seconds=self.governor.cooldown_seconds)
                    if retry:
                        try:
                            proposed=now+timedelta(seconds=float(retry))
                        except ValueError:
                            try:proposed=parsedate_to_datetime(retry)
                            except (ValueError,TypeError):proposed=deadline
                        if proposed.tzinfo is None:proposed=proposed.replace(tzinfo=timezone.utc)
                        deadline=max(deadline,proposed)
                    ledger.update(circuit_open=True,cooldown_until=deadline.isoformat())
                    _atomic_json(self.governor.path,ledger)
                raise
            fetched_at=datetime.now(timezone.utc).isoformat()
            journal.complete(key,raw_sha256=captured['raw_sha256'],row_count=0,
                             **identity,fetched_at=fetched_at,http_status=captured['http_status'],
                             response_headers=captured['response_headers'],evidence_level='HTTP_RAW',
                             qualification='TRANSPORT_CAPTURED_NOT_DATA_QUALIFIED')
            return {**journal.data['units'][key],'content':content,'cache_hit':False,'request_key':key}
