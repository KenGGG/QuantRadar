"""Submit alternating releases concurrently; the engine's shared-state lock serializes execution."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

from quantradar.backtest import run_backtest
from quantradar.datahub.service import DataHubService

old = 'Rb60ab5f94b2a612b'
new = DataHubService().releases.current()['release_id']


def execute(release):
    factor = 10 if release == old else 1
    code = f'''
def initialize(context):
    frame = get_price('600519.XSHG', start_date='2023-09-08', end_date='2023-09-08', fields=['volume', 'money', 'low', 'high'], fq='none')
    row = frame.iloc[0]
    assert row['low'] <= row['money'] / row['volume'] * {factor} <= row['high']
'''
    _, snapshot = run_backtest(code=code, start_date='2023-09-11', end_date='2023-09-11', release_id=release)
    binding = snapshot['environment']['data_release']
    assert binding['release_id'] == release
    return {'release_id': release, 'binding': binding, 'hash': snapshot['result_hash'], 'status': 'PASS'}


with ThreadPoolExecutor(max_workers=2) as executor:
    results = list(executor.map(execute, [old, new, old, new]))
assert results[0]['hash'] == results[2]['hash']
assert results[1]['hash'] == results[3]['hash']
Path('docs/acceptance/datahub-remediation-2026-09-11/concurrent-replay.json').write_text(json.dumps(results, indent=2))
print(json.dumps(results))
