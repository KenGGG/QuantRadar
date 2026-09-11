"""Exercise real engine APIs against a published release; write only /tmp reports."""
import json
from pathlib import Path

from quantradar.backtest_run import run_unified_backtest
from quantradar.datahub.service import DataHubService

release = DataHubService().releases.current()['release_id']
results = []
for name, security, day, strict, expected in [
    ('supplemental_read', '600519.XSHG', '2023-09-08', False, None),
    ('isolated_stock', '000022.XSHE', '2023-09-08', False, '隔离'),
    ('missing_date', '600519.XSHG', '2016-01-04', False, '缺少'),
    ('strict_pit', '600519.XSHG', '2023-09-08', True, '严格 PIT'),
]:
    code = f'''
from jqdatasdk import query, valuation
def initialize(context):
    inspect(context)
def inspect(context):
    q = query(valuation.code, valuation.pe_ratio).filter(valuation.code.in_([{security!r}]))
    q.quantradar_require_pit = {strict!r}
    values = get_fundamentals(q, date={day!r})
    assert len(values) == 1 and values.iloc[0]['pe_ratio'] > 0
    assert values.attrs['release_id'] == {release!r}
    sectors = get_industry([{security!r}], date={day!r})
    assert sectors[{security!r}]['sw_l1']['industry_code']
    prices = get_price({security!r}, start_date={day!r}, end_date={day!r}, fields=['volume', 'money', 'low', 'high'], fq='none')
    row = prices.iloc[0]
    assert row['low'] <= row['money'] / row['volume'] <= row['high']
'''
    try:
        output = run_unified_backtest('release_' + name, {'code': code, 'start_date': '2023-09-11', 'end_date': '2023-09-11',
            'initial_cash': 100000, 'frequency': 'day', 'fq': 'none', 'benchmark': '000300.XSHG', 'release_id': release},
            runs_dir='/tmp/quantradar-remediation-release')
        results.append({'case': name, 'status': 'FAIL' if expected else 'PASS', 'hash': output['result_hash'], 'release_id': release})
    except Exception as exc:
        results.append({'case': name, 'status': 'PASS' if expected and expected in str(exc) else 'FAIL', 'error': str(exc), 'release_id': release})
    print(json.dumps(results[-1], ensure_ascii=False), flush=True)
Path('docs/acceptance/datahub-remediation-2026-09-11/strategy-release.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
if any(r['status'] != 'PASS' for r in results):
    raise SystemExit(1)
