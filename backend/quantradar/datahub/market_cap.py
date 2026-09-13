"""Offline parsing of archived Eastmoney total-market-cap snapshots."""
from __future__ import annotations

import csv
import hashlib
import io
import math
from datetime import date
from typing import Any


def parse_eastmoney_market_cap(content: bytes, *, symbol: str, raw_sha256: str) -> list[dict[str, Any]]:
    rows = list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
    result = []
    for row in rows:
        date, cap = str(row.get('数据日期') or ''), row.get('总市值')
        if len(date) != 10 or cap in (None, ''):
            continue
        value = float(cap)
        if value < 0:
            raise ValueError('negative total market cap')
        result.append({'trade_date': date, 'symbol': symbol, 'total_market_cap_cny': value,
                       'source': 'eastmoney:RPT_VALUEANALYSIS_DET', 'raw_sha256': raw_sha256,
                       'pit_status': 'PARTIAL', 'qualification': 'CANDIDATE_NOT_PUBLISHED'})
    if not result:
        raise ValueError('no total market cap rows')
    return result


def validate_market_cap_candidate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Require archived Eastmoney *total* market cap before publication."""
    seen, errors = set(), []
    for row in rows:
        key = (str(row.get('trade_date') or '')[:10], row.get('symbol'))
        try:
            date.fromisoformat(key[0])
        except ValueError:
            errors.append('invalid trade_date')
        if not isinstance(key[1], str) or len(key[1]) != 9 or not key[1][:6].isdigit() or not key[1].endswith(('.SH', '.SZ')):
            errors.append('invalid symbol')
        if key in seen:
            errors.append('duplicate key')
        seen.add(key)
        try:
            valid_cap = math.isfinite(float(row.get('total_market_cap_cny'))) and float(row['total_market_cap_cny']) >= 0
        except (TypeError, ValueError):
            valid_cap = False
        if not valid_cap:
            errors.append('invalid total market cap')
        if row.get('source') != 'eastmoney:RPT_VALUEANALYSIS_DET' or len(str(row.get('raw_sha256') or '')) != 64:
            errors.append('missing archived provenance')
        if row.get('pit_status') != 'PARTIAL' or row.get('qualification') != 'CANDIDATE_NOT_PUBLISHED':
            errors.append('invalid qualification')
    return {'status': 'PASS' if rows and not errors else 'FAIL', 'rows': len(rows), 'errors': sorted(set(errors))}


def materialize_market_cap_catalog(catalog: dict[str, Any], *, raw_root, fetched_at: str):
    """Reparse only hash-verified archived snapshots into publishable rows."""
    for artifact in catalog.get('artifacts', []):
        if artifact.get('kind') != 'PARSED_SNAPSHOT' or artifact.get('source') != 'eastmoney:RPT_VALUEANALYSIS_DET':
            continue
        digest, symbol = str(artifact.get('sha256') or ''), str(artifact.get('symbol') or '')
        content = raw_root.joinpath(digest).read_bytes()
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError(f'archived market-cap bytes changed: {symbol}')
        for row in parse_eastmoney_market_cap(content, symbol=symbol, raw_sha256=digest):
            yield {
                **row,
                'adapter_version': 'eastmoney-archive-v1',
                'fetched_at': fetched_at,
                'available_date': None,
            }
