"""Real read-only backtest probes, with outputs isolated under /tmp."""
import json
import time
from pathlib import Path
from quantradar.backtest_run import run_unified_backtest

output = []
expected_hashes = {
    'buy_hold_raw': 'e9dfb61e0b7ab38ba94d95e14b6700b046e5ec9cead52ab01294464e071be2fe',
    'buy_hold_pre': 'e9dfb61e0b7ab38ba94d95e14b6700b046e5ec9cead52ab01294464e071be2fe',
    'low_beta': 'e24bd0d3d892ddc26c5aeafcd2b78c343e380432ebef251caa6aef1f8e07a745',
}
old_release = 'Rb60ab5f94b2a612b'
examples = [
    ('buy_hold_raw', {'security': '600519.XSHG', 'start_date': '2023-01-03', 'end_date': '2023-01-13', 'fq': 'none'}),
    ('buy_hold_pre', {'security': '600519.XSHG', 'start_date': '2023-01-03', 'end_date': '2023-01-13', 'fq': 'pre'}),
]
strategy = Path('/tmp/quantradar-low-beta-check/low_beta_september_check/strategy.py')
if strategy.exists():
    examples.append(('low_beta', {'code': strategy.read_text(), 'start_date': '2023-09-01', 'end_date': '2023-09-28', 'fq': 'none', 'initial_cash': 100000, 'benchmark': '000300.XSHG'}))
else:
    output.append({'name': 'low_beta', 'status': 'NOT_RUN', 'reason': f'User strategy source unavailable: {strategy}'})
for name, config in examples:
    started = time.monotonic()
    try:
        result = run_unified_backtest('remediation_' + name, {'initial_cash': 500000, 'frequency': 'day', 'amount': 100, 'release_id': old_release, **config}, runs_dir='/tmp/quantradar-remediation-backtests')
        assert result['result_hash'] == expected_hashes[name], 'historical result hash changed'
        output.append({'name': name, 'status': 'PASS', 'seconds': round(time.monotonic() - started, 3), 'hash': result['result_hash']})
    except Exception as exc:
        output.append({'name': name, 'status': 'FAIL', 'error': str(exc)})
    print(json.dumps(output[-1]), flush=True)
Path('docs/acceptance/datahub-remediation-2026-09-11/backtests.json').write_text(json.dumps(output, indent=2))
if any(row['status'] != 'PASS' for row in output):
    raise SystemExit(1)
