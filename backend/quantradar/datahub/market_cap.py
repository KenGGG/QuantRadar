"""Offline parsing of archived Eastmoney total-market-cap snapshots."""
from __future__ import annotations

import csv
import io
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
