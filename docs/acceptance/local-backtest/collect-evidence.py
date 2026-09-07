import csv
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen
out=Path('/data/Projects/a-stock-research/QuantRadar/docs/acceptance/local-backtest')
def get(path):
    return json.load(urlopen('http://127.0.0.1:7231'+path))
manifest={'url':'http://127.0.0.1:7231/','runs':[]}
for key in ('buyhold','dma','rebalance'):
    browser=json.loads((out/f'{key}.json').read_text())
    assert browser['browser_workflow']=='PASS'
    rid=browser['submission']['run_id']
    rec=get('/api/backtest/runs/'+rid)
    assert rec['status']=='SUCCESS',rec.get('error')
    directory=Path(rec['config']['run_dir'])
    native=json.loads((directory/'metrics.json').read_text(),parse_constant=lambda value:value)
    assert native['metrics']==rec['metrics']
    assert native['meta']['initial_total_value']==rec['config']['initial_cash']
    assert native['meta']['benchmark']==rec['config']['benchmark']
    assert (directory/'strategy.py').read_text()==browser['strategy']['source']
    snapshot=json.loads((directory/'snapshot.json').read_text())
    assert snapshot['result_hash']==rec['result_hash']
    assert snapshot['environment']['quantradar_commit'].startswith('5118bd4')
    rows=list(csv.DictReader((directory/'daily_records.csv').open(encoding='utf-8-sig')))
    trades=list(csv.DictReader((directory/'trades.csv').open(encoding='utf-8-sig')))
    positions=list(csv.DictReader((directory/'daily_positions.csv').open(encoding='utf-8-sig')))
    assert rows and trades and positions
    assert all(r.get('benchmark_value') for r in rows)
    assert len(rows)==native['metrics']['交易天数']
    assert rec['config']['start_date']<=rows[0]['date'][:10]<=rows[-1]['date'][:10]<=rec['config']['end_date']
    for report in ('full','standard'):
        with urlopen(f'http://127.0.0.1:7231/api/backtest/runs/{rid}/report?which={report}') as response:
            assert response.status==200
    artifacts={p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in directory.iterdir() if p.is_file()}
    manifest['runs'].append({'sample':key,'run_id':rid,'status':rec['status'],'version':snapshot['environment']['quantradar_commit'],'config':rec['config'],'result_hash':rec['result_hash'],'data_environment':snapshot['environment'],'records':len(rows),'trades':len(trades),'positions':len(positions),'traded_securities':sorted(set(t['标的'] for t in trades)),'metrics':rec['metrics'],'artifacts':artifacts})
recovery=json.loads((out/'recovery-failure.json').read_text())
assert recovery['browser_workflow']=='PASS'
rerun=get('/api/backtest/runs/'+recovery['recovered_submission']['run_id'])
failed=get('/api/backtest/runs/'+recovery['failed_submission']['run_id'])
assert rerun['status']=='SUCCESS'
assert rerun['result_hash']==manifest['runs'][0]['result_hash']
assert failed['status']=='FAILED' and 'browser_expected_failure' in failed['error']
manifest['recovery']={'run_id':rerun['run_id'],'result_hash':rerun['result_hash'],'same_result_hash':True}
manifest['expected_failure']={'run_id':failed['run_id'],'status':failed['status'],'error':failed['error']}
(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False))
print(json.dumps([{k:r[k] for k in ('sample','run_id','version','records','trades','positions')} for r in manifest['runs']],ensure_ascii=False,indent=2))
print('recovery and expected failure: PASS')
