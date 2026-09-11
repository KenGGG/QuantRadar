"""Stream immutable candidate evidence; no status-page database or JSONL scans."""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from datetime import date
from pathlib import Path

POLICY = 'valuation-quality-v2'
FIELDS = ('pe_ttm', 'pb_mrq', 'ps_ttm', 'pcf_ocf_ttm')


def validate_shard(path: Path, symbol: str, unit: dict, raw_store=None) -> dict:
    errors = Counter()
    nulls = Counter()
    digest = hashlib.sha256()
    economic = hashlib.sha256()
    dates = set()
    count = 0
    source_hashes = set()
    try:
        with path.open('rb') as handle:
            for line in handle:
                digest.update(line)
                count += 1
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError('row_type')
                    if row.get('symbol') != symbol or not re.fullmatch(r'\d{6}\.(SH|SZ)', symbol):
                        raise ValueError('symbol')
                    day = row['trade_date']
                    if date.fromisoformat(day).isoformat() != day:
                        raise ValueError('date')
                    if day in dates:
                        errors['duplicate_key'] += 1
                    dates.add(day)
                    if row.get('source') != 'eastmoney:RPT_VALUEANALYSIS_DET' or 'pcf_ncf_ttm' in row:
                        raise ValueError('source_or_semantics')
                    if row.get('pit_status') not in ('PARTIAL', 'PASS') or not row.get('adapter_version'):
                        raise ValueError('provenance')
                    if row.get('pit_status') == 'PASS' and not row.get('available_date'):
                        raise ValueError('unproven_pit')
                    raw_hash = row['raw_sha256']
                    if not re.fullmatch('[0-9a-f]{64}', raw_hash):
                        raise ValueError('raw_hash')
                    source_hashes.add(raw_hash)
                    values = []
                    for field in FIELDS:
                        value = row[field]
                        if value is None:
                            nulls[field] += 1
                        elif isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
                            raise ValueError('numeric_type')
                        values.append(value)
                    economic.update(json.dumps([symbol, day, values], separators=(',', ':')).encode())
                except (ValueError, TypeError, KeyError) as exc:
                    errors[str(exc)[:100]] += 1
    except OSError:
        errors['missing_file'] += 1
    expected = unit.get('staged_result_sha256')
    if not expected or digest.hexdigest() != expected:
        errors['content_hash'] += 1
    if count != unit.get('row_count') or not count:
        errors['row_count'] += 1
    if raw_store is not None:
        # Legacy archive proves normalized bytes, never original HTTP bytes.
        try:
            raw_store.read(expected or '')
        except (OSError, ValueError):
            # New runners persist the original response instead of an archive.
            try:
                for raw_hash in source_hashes:
                    raw_store.read(raw_hash)
                if not source_hashes:
                    raise ValueError('no source hashes')
            except (OSError, ValueError):
                errors['missing_raw_evidence'] += 1
    return {'status': 'FAIL' if errors else 'PASS', 'errors': dict(errors), 'rows': count,
            'first_date': min(dates, default=None), 'latest_date': max(dates, default=None),
            'source_nulls': dict(nulls), 'input_hash': digest.hexdigest(), 'economic_hash': economic.hexdigest(),
            'dates': sorted(dates), 'pit': 'PARTIAL', 'raw_http': 'NOT_CHECKED'}


def validate_candidate(root: Path, units: dict, *, base_commit: str, raw_store=None, calendar=None) -> dict:
    accepted, isolated, summaries = [], {}, {}
    identity = hashlib.sha256()
    identity.update((POLICY + base_commit).encode())
    for symbol, unit in sorted(units.items()):
        if unit.get('status') != 'COMPLETE':
            reason = unit.get('category') or ('UNVERIFIED_COVERAGE' if unit.get('status') in ('LEGAL_EMPTY', 'NOT_COVERED') else unit.get('status'))
            isolated[symbol] = reason
            identity.update(json.dumps([symbol, unit], sort_keys=True).encode())
            continue
        result = validate_shard(root / 'valuation_daily' / f'{symbol}.jsonl', symbol, unit, raw_store)
        dates = result.pop('dates')
        if calendar is not None and dates:
            expected = {d for d in calendar if dates[0] <= d <= dates[-1]}
            result['missing_internal_days'] = len(expected - set(dates))
            result['calendar_status'] = 'WARN' if expected - set(dates) else 'PASS'
        else:
            result['calendar_status'] = 'NOT_CHECKED'
        summaries[symbol] = result
        identity.update(json.dumps([symbol, result], sort_keys=True).encode())
        if result['status'] == 'PASS':
            accepted.append(symbol)
        else:
            isolated[symbol] = result['errors']
    return {'candidate_id': 'C' + identity.hexdigest(), 'base_commit': base_commit, 'policy': POLICY,
            'quality': 'PASS' if accepted else 'FAIL', 'coverage': 'PARTIAL' if isolated else 'NOT_CHECKED',
            'pit': 'PARTIAL', 'accepted': accepted, 'isolated': isolated, 'shards': summaries,
            'row_count': sum(summaries[s]['rows'] for s in accepted),
            'schema_error_count': sum(sum(v for k, v in r['errors'].items() if k != 'duplicate_key') for r in summaries.values()),
            'duplicate_count': sum(r['errors'].get('duplicate_key', 0) for r in summaries.values()),
            'rules_not_checked': ['cross_source_values', 'historical_availability', 'full_lifecycle_field_coverage']}
