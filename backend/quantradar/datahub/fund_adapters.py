"""Scoped ETF source parsers; parsed records remain candidates until qualified."""
from __future__ import annotations
import ast
import json
import math
import re
from datetime import date
from typing import Any

from .research_collection import GovernedHttpSource


def _day(value):
    text=str(value or '').strip()[:10]
    if not text or text in {'--','---'}:return None
    return date.fromisoformat(text).isoformat()


def _number(value):
    if value in (None,'','--','---'):return None
    number=float(value)
    if not math.isfinite(number):raise ValueError('non-finite source number')
    return number


def _literal_assignment(text: str, variable: str):
    match=re.search(r'(?:^|;)\s*var\s+'+re.escape(variable)+r'\s*=\s*',text)
    if not match:raise ValueError(f'missing source variable {variable}')
    # Tokenization by Python's AST rejects code/calls; source values are literal
    # nested arrays of numbers/strings. A semicolon inside a string is rejected,
    # not executed or accepted as an incomplete record.
    payload=text[match.end():].split(';',1)[0].strip()
    try:value=ast.literal_eval(payload)
    except (ValueError,SyntaxError,MemoryError,RecursionError) as exc:raise ValueError('invalid literal source array') from exc
    if not isinstance(value,list):raise ValueError('source array required')
    return value


def parse_fund_event_page(content: bytes, *, kind: str, year: int, page: int) -> dict:
    if kind not in {'dividend','split'} or not 1990<=year<=2100 or page<1:
        raise ValueError('explicit kind/year/page required')
    if len(content)>16_000_000:raise ValueError('event response size exceeded')
    text=content.decode('utf-8-sig');prefix='jjfh' if kind=='dividend' else 'jjcf'
    # Eastmoney's historical response used ``jjfh_jjjs``/``jjcf_jjjs``;
    # current responses expose the same page-count tuple as ``pageinfo``.
    metadata=_literal_assignment(text,'pageinfo') if re.search(r'(?:^|;)\s*var\s+pageinfo\s*=',text) else _literal_assignment(text,prefix+'_jjjs')
    if not metadata or isinstance(metadata[0],bool) or not isinstance(metadata[0],int) or not 0<=metadata[0]<=10000:
        raise ValueError('invalid pagination metadata')
    pages=metadata[0]
    if page>max(1,pages):raise ValueError('page beyond reported total')
    source_rows=_literal_assignment(text,prefix+'_data')
    if pages==0 and source_rows:raise ValueError('records with zero pages')
    result=[];keys=set()
    for row in source_rows:
        width=7 if kind=='dividend' else 6
        if not isinstance(row,list) or len(row)!=width:raise ValueError('event row schema width changed')
        code=str(row[0])
        if not re.fullmatch(r'\d{6}',code):raise ValueError('invalid fund share-class code')
        event=dict(fund_code=code,source_name=row[1],kind=kind,source_year=year,
                   cash_per_unit=None,record_date=None,ex_date=None,pay_date=None,
                   share_multiplier=None,qualification='ANNOUNCEMENT_UNVERIFIED',
                   available_at=None,evidence_level='HTTP_RAW')
        if kind=='dividend':
            event.update(record_date=_day(row[2]),ex_date=_day(row[3]),cash_per_unit=_number(row[4]),pay_date=_day(row[5]),source_unit='CNY_PER_FUND_UNIT')
        else:
            event.update(ex_date=_day(row[2]),source_split_type=row[3],source_split_value=_number(row[4]))
        key=(code,event['ex_date'],event['record_date'],event['pay_date'],kind)
        if key in keys:raise ValueError('duplicate event key')
        keys.add(key);result.append(event)
    return dict(kind=kind,year=year,page=page,page_count=pages,pagination_metadata=metadata,
                total_count_semantics='UNVERIFIED',rows=result,
                coverage_status='SOURCE_EMPTY_NOT_EVENT_ABSENCE_PROOF' if not result else 'PAGE_CAPTURED')


def parse_etf_daily(payload: dict, *, symbol: str, start: str, end: str) -> list[dict]:
    if not re.fullmatch(r'\d{6}\.(SH|SZ)',symbol):raise ValueError('explicit ETF exchange required')
    data=payload.get('data')
    if payload.get('rc')!=0 or not isinstance(data,dict) or not data.get('klines'):
        raise ValueError('empty/unusable ETF daily response; coverage unknown')
    expected_market=1 if symbol.endswith('.SH') else 0
    if data.get('code')!=symbol[:6] or data.get('market')!=expected_market:
        raise ValueError('ETF response security identity mismatch')
    rows=[];seen=set()
    for line in data['klines']:
        fields=line.split(',')
        if len(fields)!=11:raise ValueError('ETF daily schema width changed')
        day=_day(fields[0])
        if day is None:raise ValueError('missing trade date')
        if day in seen:raise ValueError('duplicate ETF trade date')
        seen.add(day)
        values=list(map(_number,fields[1:]))
        if any(v is None for v in values[:6]):raise ValueError('missing required ETF raw fields')
        op,cl,hi,lo,vol,amount=values[:6]
        if not 0<lo<=min(op,cl)<=max(op,cl)<=hi or vol<0 or amount<0:
            raise ValueError('invalid ETF OHLC/quantity bounds')
        if not start<=day<=end:raise ValueError('ETF response outside requested dates')
        rows.append(dict(symbol=symbol,trade_date=day,open=op,close=cl,high=hi,low=lo,
                         volume_source=vol,amount_source=amount,volume_units=None,amount_cny=None,
                         unit_status='UNIT_UNVERIFIED',adjustment='raw',pit_status='PARTIAL',available_at=None))
    if [r['trade_date'] for r in rows]!=sorted(seen):raise ValueError('unordered ETF dates')
    return rows


def qualify_etf_daily_units(rows: list[dict]) -> list[dict]:
    """Accept hand/yuan only when the source's price-volume identity proves it.

    The Eastmoney daily response does not carry a machine-readable unit label.
    For an ETF, ``amount / (close * volume)`` must be near 100 for hand volume
    and yuan amount.  It is not exactly 100 because amount uses the intraday
    volume-weighted price rather than the close.  Zero-volume observations are
    not evidence.
    """
    evidence=[]
    for row in rows:
        volume, amount, close = row.get('volume_source'), row.get('amount_source'), row.get('close')
        if volume is None or amount is None or close is None:
            raise ValueError('ETF unit qualification requires price, volume and amount')
        if volume > 0 and amount > 0 and close > 0:
            evidence.append(float(amount)/(float(close)*float(volume)))
    if not evidence or any(not 85.0 <= value <= 115.0 for value in evidence):
        raise ValueError('ETF source units are not consistently hand/yuan')
    result=[]
    for row in rows:
        item=dict(row)
        item.update(volume_shares=float(row['volume_source'])*100.0,
                    amount_cny=float(row['amount_source']),
                    volume_units='HAND',
                    unit_status='HAND_AND_CNY_QUALIFIED')
        result.append(item)
    return result


def validate_etf_daily_candidate(rows: list[dict]) -> dict:
    """Reject incomplete ETF daily records before any supplemental write."""
    errors=[];seen=set()
    for row in rows:
        day,symbol=str(row.get('trade_date') or '')[:10],row.get('symbol')
        try: date.fromisoformat(day)
        except ValueError: errors.append('invalid trade_date')
        if not isinstance(symbol,str) or not re.fullmatch(r'\d{6}\.(SH|SZ)',symbol): errors.append('invalid symbol')
        if (day,symbol) in seen: errors.append('duplicate key')
        seen.add((day,symbol))
        values=[]
        try:
            values=[float(row[field]) for field in ('open','high','low','close','volume_shares','amount_cny')]
        except (TypeError,ValueError):
            errors.append('invalid normalized quantity')
        if values and (not all(math.isfinite(value) and value >= 0 for value in values) or
                       values[2] > min(values[0],values[3]) or values[1] < max(values[0],values[3])):
            errors.append('invalid normalized quantity')
        if row.get('source')!='eastmoney:push2his_etf_kline' or len(str(row.get('raw_sha256') or ''))!=64 or not row.get('adapter_version') or not row.get('fetched_at'):
            errors.append('missing raw provenance')
        if row.get('unit_status')!='HAND_AND_CNY_QUALIFIED' or row.get('adjustment')!='raw' or row.get('pit_status')!='PARTIAL':
            errors.append('invalid qualification')
    return {'status':'PASS' if rows and not errors else 'FAIL','rows':len(rows),'errors':sorted(set(errors))}


class EastmoneyFundAdapter:
    """One request per call; the caller qualifies scope before iterating symbols/pages."""
    def __init__(self, transport: GovernedHttpSource):self.transport=transport

    def daily(self,symbol: str,start: str,end: str):
        if not re.fullmatch(r'\d{6}\.(SH|SZ)',symbol):raise ValueError('explicit identity required')
        params={'fields1':'f1,f2,f3,f4,f5,f6','fields2':'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f116',
                'ut':'7eea3edcaed734bea9cbfc24409ed989','klt':'101','fqt':'0',
                'beg':start.replace('-',''),'end':end.replace('-',''),
                'secid':f"{1 if symbol.endswith('.SH') else 0}.{symbol[:6]}"}
        receipt=self.transport.fetch('https://push2his.eastmoney.com/api/qt/stock/kline/get',params,contract='akshare-1.18.94-etf-raw-http-v1')
        rows=parse_etf_daily(json.loads(receipt['content']),symbol=symbol,start=start,end=end)
        return receipt,rows

    def events_page(self,kind: str,year: int,page: int):
        if kind not in {'dividend','split'} or page<1:raise ValueError('explicit event kind and page required')
        params={'dt':'8' if kind=='dividend' else '9','page':str(page),
                'rank':'BZDM' if kind=='dividend' else 'FSRQ','sort':'asc','gs':'','ftype':'','year':str(year)}
        receipt=self.transport.fetch('https://fund.eastmoney.com/Data/funddataIndex_Interface.aspx',params,contract='fund-event-literal-pages-v1')
        return receipt,parse_fund_event_page(receipt['content'],kind=kind,year=year,page=page)
