"""Bounded probes through the installed, approved SDK; never reclassify the journal."""
import importlib
import json
from pathlib import Path

from quantradar.datahub.governor import RequestGovernor
from quantradar.datahub.service import DataHubService
from quantradar.datahub.store import UpdateJournal

service = DataHubService()
journal = UpdateJournal(Path(service.config.journal_root) / 'valuation_daily-mvp.json')
symbols = ['000022.SZ', '300114.SZ', '600001.SH']
if any(journal.data['units'].get(s, {}).get('status') != 'FAILED' for s in symbols):
    raise RuntimeError('diagnostic selection must still belong to the failure baseline')
module = importlib.import_module('akshare.stock_feature.stock_value_em')
original = module.make_request_with_retry_json
governor = RequestGovernor(Path(service.config.supplemental_repo) / 'governance', 'eastmoney')
results = []
with service._updater_lock(), governor.operation_lock():
    for symbol in symbols:
        captured = []
        def capture(*args, **kwargs):
            value = original(*args, **kwargs)
            captured.append(value)
            return value
        module.make_request_with_retry_json = capture
        try:
            frame = governor.call('diagnose/' + symbol, lambda: module.stock_value_em(symbol[:6]), max_attempts=1, http_attempts_known=False)
            result = {'symbol': symbol, 'status': 'RETURNED', 'rows': len(frame)}
        except Exception as exc:
            result = {'symbol': symbol, 'status': 'FAILED', 'error': str(exc)}
        finally:
            module.make_request_with_retry_json = original
        if captured:
            content = json.dumps(captured, ensure_ascii=False, sort_keys=True).encode()
            receipt = service.raw.put('diagnostic/parsed-sdk-response/' + symbol, content)
            result.update(parsed_sdk_response=captured, sha256=receipt['sha256'], raw_http='NOT_CAPTURED')
        results.append(result)
Path('docs/acceptance/datahub-remediation-2026-09-11/failure-probes.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
print(json.dumps(results, ensure_ascii=False))
