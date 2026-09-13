#!/usr/bin/env python3
"""Read fixed local releases into research gap artifacts; never call external APIs.

The output is a reproducible staging cache and audit, not a published fact store.
Invoke from the repository's existing virtualenv. Identical cache files are reused.
"""
from __future__ import annotations
import argparse
import csv
import gzip
import hashlib
import io
import json
from collections import Counter, defaultdict
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import pymysql
from quantradar.config import load_datahub_config
from quantradar.datahub.release import ReleaseStore
from quantradar.datahub.store import RawStore, _atomic_json
from quantradar.datahub.research_inventory import snapshot_members, research_dependencies, field_gap_runs

ETF_CANDIDATES = ['510050.SH','510300.SH','510500.SH','159919.SZ','159915.SZ',
                  '159901.SZ','159902.SZ','159903.SZ','510180.SH','510880.SH']
PRICE_FIELDS = ['open','high','low','close','volume','amount','adjclose']


def dump(path, value):
    _atomic_json(path, value)


def numeric_rows(content, day_field, rename=None):
    rows={}
    for raw in csv.DictReader(io.StringIO(content.decode('utf-8-sig'))):
        day=raw.get(day_field, '')[:10]
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day): raise ValueError('raw invalid date')
        row={}
        for k,v in raw.items():
            key=(rename or {}).get(k,k)
            try: row[key]=float(v) if v not in (None,'','None','null') else None
            except (ValueError,TypeError): row[key]=v
        if day in rows: raise ValueError('duplicate raw date')
        rows[day]=row
    return rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--release',default='R22a53f013266373d')
    args=parser.parse_args(); out=args.output;out.mkdir(parents=True,exist_ok=True)
    from quantradar.datahub.alpha101.catalog import dependency_matrix
    matrix=dependency_matrix(); lookback=max(r['lookback_days'] for r in matrix)
    cfg=load_datahub_config(); manifest=ReleaseStore(cfg.release_root).resolve(args.release)
    identity={k:manifest[k] for k in ('release_id','base_commit','supplemental_commit')}
    identity['price_units']=manifest['metadata'].get('price_units')
    identity['manifest_sha256']=hashlib.sha256(ReleaseStore._canonical(manifest)).hexdigest()
    frozen=out/'frozen_release.json'
    if frozen.exists() and json.loads(frozen.read_text())!=identity: raise ValueError('output belongs to another fixed release')
    dump(frozen,identity)
    dump(out/'alpha101_dependency_matrix.json',{'formulas':matrix})
    with (out/'alpha101_dependency_matrix.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(matrix[0]));writer.writeheader();writer.writerows(matrix)
    def connect(base=True):
        return pymysql.connect(host=cfg.base_host if base else cfg.supplemental_host,
            port=cfg.base_port if base else cfg.supplemental_port,user=cfg.user,password=cfg.password,
            database=f"{cfg.base_database}/{identity['base_commit']}" if base else f"{cfg.supplemental_database}/{identity['supplemental_commit']}",
            connect_timeout=cfg.connect_timeout,read_timeout=120,cursorclass=pymysql.cursors.DictCursor)
    base,supp=connect(),connect(False)
    def query(c,q,params=()):
        with c.cursor() as cur:cur.execute(q,params);return cur.fetchall()
    schemas={}
    for label,c in [('base',base),('supplement',supp)]:
        schemas[label]={}
        for row in query(c,'SHOW TABLES'):
            table=next(iter(row.values()))
            if not re.fullmatch('[A-Za-z0-9_]+',table):raise ValueError('unsafe table name')
            schemas[label][table]=[r['Field'] for r in query(c,f'SHOW COLUMNS FROM `{table}`')]
    dump(out/'schemas.json',schemas)
    calendar=[str(r['date'])[:10] for r in query(base,"SELECT date FROM ts_trade_day_calendar WHERE exchange='SSE' AND is_open=1 AND date BETWEEN '2010-01-01' AND '2026-09-11' ORDER BY date")]
    evaluation=[d for d in calendar if '2020-01-01'<=d<='2026-08-31']
    idxrows=query(base,"SELECT stock_code,trade_date,weight FROM ts_index_weight WHERE index_code='000905.SH' AND trade_date BETWEEN '2010-01-01' AND '2026-08-31' ORDER BY trade_date,stock_code")
    snaps=defaultdict(list)
    for row in idxrows:snaps[str(row['trade_date'])[:10]].append(row['stock_code'])
    members={d:snapshot_members(snaps,d,max_age_days=45) for d in evaluation}
    candidates={d:r['symbols'] for d,r in members.items()}
    dep=research_dependencies(calendar,candidates,lookback_bars=lookback,label_sessions=5)
    formation=dep['formation'];symbols=sorted(formation)
    start=min(d for ds in formation.values() for d in ds);end=max(d for ds in dep['label'].values() for d in ds)
    dump(out/'experiment.json',dict(**identity,evaluation_start='2020-01-01',evaluation_end='2026-08-31',
         oos_start='2024-01-01',definition='CSI500_STORED_SNAPSHOT_RESEARCH_V1',lookback_bars=lookback,
         price_start=start,price_end=end,label_sessions=5,index_freshness_policy_days=45,
         universe_qualification='OBSERVED_ASOF_PARTIAL; effective and available dates unverified',
         history_pool_complete=False,selection_basis='stored historic snapshots; no performance selection',
         etf_selection_basis='fixed 10 domestic equity candidate funds; identity and lifetime require evidence',
         etf_candidates=ETF_CANDIDATES,alpha_union=symbols))
    dump(out/'calendar.json',{'dates':calendar})
    dump(out/'candidate_membership.json',{'days':members})
    dump(out/'research_dependencies.json',dep)
    print('frozen',identity['release_id'],'lookback',lookback,'union',len(symbols),'range',start,end,flush=True)
    raw=RawStore(cfg.raw_root)
    valuation=json.loads((Path(cfg.journal_root)/'valuation_daily-mvp.json').read_text())
    raw_status={}
    for p in sorted(Path(cfg.journal_root).glob('low-beta*.json')):
        j=json.loads(p.read_text())
        for symbol,detail in j.get('units',{}).items():
            if detail.get('status')=='COMPLETE' and detail.get('raw_sha256'):
                raw_status[symbol]=detail
    total=Counter(); raw_catalog=[]; index_rows=[]; files=[]
    cache=out/'base-cache';cache.mkdir(exist_ok=True)
    def cache_path(table,symbol):
        return cache/f'{table}-{symbol}-{start}-{end}.json.gz'

    def prime_base_cache(table, columns, chunk_size=100):
        """Fill missing per-symbol cache files with bounded read-only batch queries."""
        missing=[symbol for symbol in symbols if not cache_path(table,symbol).exists()]
        if not missing:
            return
        by_internal={symbol[-2:]+symbol[:6]:symbol for symbol in missing}
        for offset in range(0,len(missing),chunk_size):
            chunk=missing[offset:offset+chunk_size]
            internals=[symbol[-2:]+symbol[:6] for symbol in chunk]
            placeholders=','.join(['%s']*len(internals))
            rows=query(base,
                f'SELECT symbol,tradedate,{",".join(columns)} FROM {table} '
                f'WHERE symbol IN ({placeholders}) AND tradedate BETWEEN %s AND %s ORDER BY symbol,tradedate',
                (*internals,start,end))
            grouped=defaultdict(dict)
            for row in rows:
                symbol=by_internal[str(row.pop('symbol'))]
                grouped[symbol][str(row.pop('tradedate'))[:10]]=row
            for symbol in chunk:
                with gzip.open(cache_path(table,symbol),'wt') as f:
                    json.dump(grouped[symbol],f,allow_nan=False,default=str)
            print('cached',table,min(offset+chunk_size,len(missing)),'/',len(missing),flush=True)

    # The original audit queried three tables per security.  Pre-fill the exact
    # same immutable per-security cache in batches so an interrupted audit can
    # resume quickly without changing its inputs or output semantics.
    for table,columns in (
        ('final_a_stock_eod_price',PRICE_FIELDS),
        ('bao_a_stock_eod_info',['tradestatus','is_st']),
        ('final_a_stock_limit',['up_limit','down_limit']),
    ):
        prime_base_cache(table,columns)

    extra_by_symbol=defaultdict(dict)
    for offset in range(0,len(symbols),500):
        chunk=symbols[offset:offset+500]
        placeholders=','.join(['%s']*len(chunk))
        for row in query(supp,
            'SELECT symbol,trade_date,tradestatus,is_st FROM qr_trade_status_daily '
            f'WHERE symbol IN ({placeholders})',chunk):
            symbol=str(row.pop('symbol'))
            extra_by_symbol[symbol][str(row.pop('trade_date'))[:10]]=row
    def cached(table,symbol,columns):
        path=cache_path(table,symbol)
        if path.exists():
            with gzip.open(path,'rt') as f:return json.load(f)
        internal=symbol[-2:]+symbol[:6]
        rows=query(base,f'SELECT tradedate,{",".join(columns)} FROM {table} WHERE symbol=%s AND tradedate BETWEEN %s AND %s ORDER BY tradedate',(internal,start,end))
        mapping={str(r.pop('tradedate'))[:10]:r for r in rows}
        with gzip.open(path,'wt') as f:json.dump(mapping,f,allow_nan=False,default=str)
        return mapping
    gapfile=out/'alpha101_field_gaps.jsonl.gz'
    with gzip.open(gapfile,'wt') as f:
        for i,symbol in enumerate(symbols):
            price=cached('final_a_stock_eod_price',symbol,PRICE_FIELDS)
            state=cached('bao_a_stock_eod_info',symbol,['tradestatus','is_st'])
            limits=cached('final_a_stock_limit',symbol,['up_limit','down_limit'])
            for day,r in extra_by_symbol[symbol].items():
                state.setdefault(day,{}).update({k:v for k,v in r.items() if v is not None and state.get(day,{}).get(k) is None})
            raw_daily={}
            if symbol in raw_status:
                detail=raw_status[symbol]
                try:
                    content=raw.read(detail['raw_sha256'])
                except FileNotFoundError:
                    raw_catalog.append(dict(symbol=symbol,kind='MISSING_REFERENCED_ARTIFACT',source='baostock',sha256=detail['raw_sha256']))
                else:
                    raw_daily=numeric_rows(content,'date',{'isST':'is_st'})
                    raw_catalog.append(dict(symbol=symbol,kind='SDK_RESPONSE_SNAPSHOT',source='baostock',sha256=detail['raw_sha256'],rows=len(raw_daily),fields=sorted(next(iter(raw_daily.values()),{}))))
            cap={}; v=valuation['units'].get(symbol,{})
            if v.get('status')=='COMPLETE':
                try:
                    content=raw.read(v['raw_sha256'])
                except FileNotFoundError:
                    raw_catalog.append(dict(symbol=symbol,kind='MISSING_REFERENCED_ARTIFACT',source='eastmoney:RPT_VALUEANALYSIS_DET',sha256=v['raw_sha256']))
                else:
                    cap=numeric_rows(content,'数据日期',{'总市值':'market_cap','流通市值':'float_market_cap','总股本':'total_shares','流通股本':'float_shares'})
                    raw_catalog.append(dict(symbol=symbol,kind='PARSED_SNAPSHOT',source='eastmoney:RPT_VALUEANALYSIS_DET',sha256=v['raw_sha256'],rows=len(cap),fields=sorted(next(iter(cap.values()),{}))))
            domains=[('formation',PRICE_FIELDS,price,raw_daily),('formation',['tradestatus','is_st'],state,raw_daily),
                     ('formation',['market_cap'],{},cap),('execution',['open','close'],price,raw_daily),
                     ('execution',['tradestatus','is_st'],state,raw_daily),('execution',['up_limit','down_limit'],limits,{}),
                     ('label',['open','close'],price,raw_daily)]
            counts=Counter()
            for purpose,fields,source,raw_rows in domains:
                for run in field_gap_runs(symbol,dep[purpose][symbol],fields,source,purpose=purpose,raw_rows=raw_rows):
                    counts[run['action']]+=run['key_count'];total[run['action']]+=run['key_count'];f.write(json.dumps(run)+'\n')
            # Cannot decide event absence or historical hierarchy from a missing source table.
            for field in ['corporate_actions','indclass.sector','indclass.industry','indclass.subindustry']:
                run=dict(symbol=symbol,field=field,purpose='formation',action='UNKNOWN',start_date=formation[symbol][0],end_date=formation[symbol][-1],key_count=len(formation[symbol]))
                counts['UNKNOWN']+=run['key_count'];total['UNKNOWN']+=run['key_count'];f.write(json.dumps(run)+'\n')
            index_rows.append(dict(symbol=symbol,counts=dict(counts)))
            if i%50==0:print('inventory',i+1,'/',len(symbols),flush=True)
    base.close();supp.close()
    dump(out/'raw_catalog.json',{'artifacts':raw_catalog})
    dump(out/'alpha101_gap_plan.json',dict(**identity,status='SCANNED_NOT_QUALIFIED',definition='CSI500_STORED_SNAPSHOT_RESEARCH_V1',
         symbols=len(symbols),evaluation_dates=len(evaluation),candidate_date_keys=sum(map(len,candidates.values())),
         max_lookback_bars=lookback,dependencies='research_dependencies.json',gap_runs=gapfile.name,
         counts=dict(total),per_symbol=index_rows,boundary_errors=dep['boundary_errors'],
         stale_membership_dates=sum(r['status']=='STALE' for r in members.values()),
         pit_grade='PARTIAL',formula_groups=dict(Counter(r['group'] for r in matrix)),
         limitations=['Snapshot effective/publication times not qualified','Per-formula readiness must filter its own fields and lookback','Event absence not established','Listing evidence not applied: no denominator shrink'] ))
    first=calendar.index(evaluation[0]);etf_days=calendar[first-60:calendar.index(evaluation[-1])+2]
    etf_fields={'formation':['open','high','low','close','volume_units','amount_cny'],
                'execution':['tradestatus','up_limit','down_limit','tick_size','lot_size','fees','corporate_actions'],
                'identity':['listing_date','termination_date','share_class','tracking_index','currency','asset_class']}
    eruns=[]
    for symbol in ETF_CANDIDATES:
        for purpose,fields in etf_fields.items():
            for field in fields:
                eruns.append(dict(symbol=symbol,field=field,purpose=purpose,action='FETCH' if purpose=='formation' else 'UNKNOWN',start_date=etf_days[0],end_date=etf_days[-1],key_count=len(etf_days)))
    dump(out/'etf_rotation_gap_plan.json',dict(**identity,status='SCOPED_NOT_QUALIFIED',symbols=ETF_CANDIDATES,
        selection_rule='fixed domestic equity candidate list before observing returns',evaluation_dates=evaluation,
        warmup_sessions=60,calendar_dates=etf_days,identity_unverified=True,required=eruns,
        counts=dict(Counter({action:sum(r['key_count'] for r in eruns if r['action']==action) for action in ['FETCH','UNKNOWN']})),
        nav_required=False,base_price_rows=0,base_price_evidence='G0 query on final table for all ten exact SH/SZ symbols',
        limitations=['Current fund list is not historical universe','Prelisting not removed until official evidence','10-code selection is research scope, not complete ETF population']))
    dump(out/'field_coverage.json',{'alpha':dict(total),'etf':{'price':'MISSING_IN_BASE_FINAL','identity':'UNKNOWN','events':'UNKNOWN'},'raw_reuse_artifacts':len(raw_catalog),'transport_requests':0})
    print('plans complete',dict(total),flush=True)


if __name__=='__main__':main()
