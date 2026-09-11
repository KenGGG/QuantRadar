"""Export a read-only failure baseline from the deployed configuration."""
import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
from collections import Counter
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pid', type=int)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.pid:
        for item in Path(f'/proc/{args.pid}/environ').read_bytes().split(b'\0'):
            if b'=' in item:
                key, value = item.decode().split('=', 1)
                if key.startswith('DATAHUB_'):
                    os.environ[key] = value
    from quantradar.config import load_datahub_config
    config = load_datahub_config()
    path = Path(config.journal_root) / 'valuation_daily-mvp.json'
    content = path.read_bytes()
    journal = json.loads(content)
    args.output.mkdir(parents=True, exist_ok=True)
    baseline = args.output / 'journal-baseline.json'
    if baseline.exists():
        raise RuntimeError('baseline already exists; refusing to overwrite')
    baseline.write_bytes(content)
    fields = ['dataset', 'symbol', 'status', 'range_start', 'range_end', 'error', 'fingerprint', 'category', 'adapter_version', 'raw_status', 'first_failure', 'last_failure', 'attempts', 'next_action']
    groups = Counter()
    with (args.output / 'baseline_failures.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        for symbol, unit in sorted(journal['units'].items()):
            if unit.get('status') != 'FAILED':
                continue
            error = str(unit.get('error', ''))
            fingerprint = error.replace(symbol, '<symbol>')
            groups[(unit.get('adapter_version', 'UNKNOWN'), fingerprint)] += 1
            writer.writerow(dict(dataset='valuation_daily', symbol=symbol, status='FAILED', range_start=unit.get('first_date', 'UNKNOWN'), range_end=unit.get('last_date', 'UNKNOWN'), error=error, fingerprint=fingerprint, category=unit.get('category', 'UNRESOLVED'), adapter_version=unit.get('adapter_version', 'UNKNOWN'), raw_status=unit.get('raw_status', 'UNKNOWN'), first_failure=unit.get('first_failed_at', 'UNKNOWN'), last_failure=unit.get('request_finished_at', 'UNKNOWN'), attempts=unit.get('attempts', 'UNKNOWN'), next_action='isolate; diagnose representative raw/SDK evidence'))
    report = {'journal_path': str(path), 'baseline_sha256': hashlib.sha256(content).hexdigest(), 'installed_akshare': importlib.metadata.version('akshare'), 'states': dict(Counter(u.get('status') for u in journal['units'].values())), 'groups': [{'adapter_version': key[0], 'fingerprint': key[1], 'count': count} for key, count in groups.items()], 'legacy_gaps': {symbol: u for symbol, u in journal['units'].items() if u.get('status') in {'NOT_COVERED', 'LEGAL_EMPTY'}}}
    (args.output / 'failure_groups.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != 'legacy_gaps'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
