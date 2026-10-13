"""Resumable, predeclared comparisons submitted through the real research API."""
import argparse
import ast
import hashlib
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/acceptance/quantradar2-etf-evidence'
URL = 'http://127.0.0.1:7242/api/v2'
ORIGINAL = '20629e741dc54ccdbbe14397c642bca9'
POOL = ['512890.XSHG','159949.XSHE','513100.XSHG','518880.XSHG']

def api(path, payload=None):
    request = urllib.request.Request(URL+path, data=None if payload is None else json.dumps(payload).encode(),
                                     headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)

def save(value):
    OUT.mkdir(parents=True, exist_ok=True)
    temp = OUT / 'manifest.tmp'
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(OUT/'manifest.json')

def cases():
    controls = [(f'hold_{s[:6]}', {'mode':'hold','security':s}) for s in POOL]
    controls += [('equal_monthly', {'mode':'equal'}), ('momentum_25', {'mode':'momentum'})]
    result = [{'key':'original_full','kind':'original','extras':{},'bars':84}]
    result += [{'key':key,'kind':'control','extras':extras} for key,extras in controls]
    variants = [('bias_48', {'bias_n':48}), ('bias_72', {'bias_n':72}),
                ('momentum_20', {'momentum_n':20}), ('momentum_30', {'momentum_n':30}),
                ('switch_1.2', {'switch_ratio':1.2}), ('switch_1.8', {'switch_ratio':1.8}),
                ('weights_equal', {'weights':[1/3,1/3,1/3]}),
                ('weights_efficiency_60', {'weights':[.2,.2,.6]})]
    result += [{'key':key,'kind':'original','extras':extras} for key,extras in variants]
    result += [{'key':f'cost_{m}x','kind':'cost','multiplier':m,'extras':{}} for m in [2,3]]
    result += [{'key':'original_start_2022','kind':'original','extras':{},'start':'2022-01-01'}]
    result += [{'key':'followup_original','kind':'original','extras':{},'start':'2025-12-08','end':'2026-10-12'}]
    result += [{'key':'followup_'+key,'kind':'control','extras':extras,'start':'2025-12-08','end':'2026-10-12'} for key,extras in controls]
    assert len(result) == 25
    for case in result:
        case.setdefault('start', '2019-01-01')
        case.setdefault('end', '2025-12-05')
        case.setdefault('bars', 96)
    return result

def submit():
    if (OUT/'manifest.json').exists():
        raise RuntimeError('Manifest already exists; use monitor, do not duplicate submissions')
    original = api('/revisions/'+ORIGINAL)
    source = original['source']
    # Verify this is exactly the immutable source of the previously analysed run.
    old = ROOT/'var/quantradar2/runs/5895a74a4635451f9b3e958d4e09143b/strategy.py'
    # Windows task writes can expand existing CRLF. Compare parsed programs,
    # while preserving and hashing the exact immutable revision for submission.
    assert ast.dump(ast.parse(source)) == ast.dump(ast.parse(old.read_text(encoding='utf-8')))
    baseline = (ROOT/'examples/v2/etf_evidence_baseline.py').read_text(encoding='utf-8')
    manifest = {'original_revision':ORIGINAL,'original_source_sha256':hashlib.sha256(source.encode()).hexdigest(),
                'design':'25 predeclared real API backtests; no parameter selection after observing results',
                'followup_is_retrospective':True,'cases':cases()}
    save(manifest)
    for case in manifest['cases']:
        own = baseline if case['kind']=='control' else source
        if case['kind']=='cost':
            m = case['multiplier']
            assert own.count('FixedSlippage(0.001)') == 1
            own = own.replace('FixedSlippage(0.001)',f'FixedSlippage({.001*m})')
            for field in ['open_commission','close_commission']:
                assert own.count(field+'=0.0003') == 1
                own = own.replace(field+'=0.0003',field+'='+str(.0003*m))
            own = own.replace('min_commission=5','min_commission='+str(5*m))
        strategy = api('/strategies', {'name':'验证ETF · '+case['key'],'source':own})
        case['strategy_id'] = strategy['id']
        case['revision_id'] = strategy['revision_id']
        case['source_sha256'] = hashlib.sha256(own.encode()).hexdigest()
        extras = dict(case['extras'])
        if case['kind']=='control':
            extras['earliest'] = max(case['start'], '2019-05-29')
        case['submitted_extras'] = extras
        save(manifest)
        request = {'revision_id':case['revision_id'],'start_date':case['start'],'end_date':case['end'],
                   'initial_cash':500000,'frequency':'day','benchmark':'000300.XSHG','extras':extras,
                   'data_mode':'prepared','reference_date':'2026-10-12',
                   'data_requirements':{'securities':POOL+['000300.XSHG'],'warmup_bars':case['bars']}}
        run = api('/runs', request)
        case['run_id'] = run['id']
        case['status'] = run['status']
        save(manifest)
        print('SUBMITTED', case['key'], run['id'], flush=True)
    monitor()

def monitor():
    manifest = json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
    if any('run_id' not in c for c in manifest['cases']):
        raise RuntimeError('Partial submission requires investigation; do not silently resubmit')
    last = None
    while True:
        pending = []
        for case in manifest['cases']:
            if case.get('status') in ['SUCCEEDED','FAILED','CANCELLED','INTERRUPTED']:
                continue
            run = api('/runs/'+case['run_id'])
            case['status'] = run['status']
            if run.get('error'): case['error'] = run['error']
            if run['status']=='SUCCEEDED':
                case['finished_at'] = run['finished_at']
            elif run['status'] in ['RUNNING','QUEUED']:
                pending.append(case)
        save(manifest)
        state = [(c['key'],c['status']) for c in manifest['cases']]
        if state != last:
            print('STATUS', json.dumps(state), flush=True)
            last = state
        if not pending:
            print('ALL TERMINAL', flush=True)
            return
        time.sleep(5)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['submit','monitor'])
    args=parser.parse_args()
    submit() if args.action=='submit' else monitor()
