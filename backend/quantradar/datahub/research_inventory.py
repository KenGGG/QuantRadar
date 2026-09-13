"""Exact research dependencies and field-level gaps, without transport or writes.

Intervals compress runs of *requested trading dates*, not calendar-day claims.
Unknown and stale membership retain their candidate denominator for auditing.
"""
from __future__ import annotations

from bisect import bisect_right
from datetime import date
import math
from typing import Any, Mapping


def _present(value: Any) -> bool:
    if value is None or value == '':
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    if isinstance(value, str):
        try:
            return math.isfinite(float(value))
        except ValueError:
            return value.strip().lower() not in {'none', 'null', 'unknown'}
    return True


def field_gap_runs(symbol: str, days: list[str], fields: list[str], rows: Mapping[str, dict], *,
                   purpose: str, raw_rows: Mapping[str, dict] | None = None,
                   listing_date: str | None = None, delisting_date: str | None = None,
                   lifecycle_evidence: str | None = None) -> list[dict]:
    """Classify every requested key. A source's finite value is inventory, not QA."""
    if (listing_date or delisting_date) and not lifecycle_evidence:
        raise ValueError('lifecycle evidence required for NOT_APPLICABLE')
    if len(days) != len(set(days)) or days != sorted(days):
        raise ValueError('days must be unique and sorted')
    if len(fields) != len(set(fields)):
        raise ValueError('fields must be unique')
    result: list[dict] = []
    for field in fields:
        previous = None
        for day in days:
            if listing_date and day < listing_date or delisting_date and day >= delisting_date:
                action = 'NOT_APPLICABLE'
            elif _present(rows.get(day, {}).get(field)):
                action = 'REUSE'
            elif _present((raw_rows or {}).get(day, {}).get(field)):
                action = 'REPARSE_RAW'
            else:
                action = 'FETCH'
            if action != previous:
                result.append(dict(symbol=symbol, field=field, purpose=purpose, action=action,
                                   start_date=day, end_date=day, key_count=1))
            else:
                result[-1]['end_date'] = day
                result[-1]['key_count'] += 1
            previous = action
    return result


def snapshot_members(snapshots: Mapping[str, list[str]], as_of: str, *, max_age_days: int) -> dict:
    """Research as-of selection; freshness policy is not adjustment-date evidence."""
    if max_age_days < 0:
        raise ValueError('max_age_days must be nonnegative')
    observed = sorted(snapshots)
    pos = bisect_right(observed, as_of) - 1
    if pos < 0:
        return dict(status='UNKNOWN', symbols=[], snapshot_date=None, strict_pit_ready=False)
    snap = observed[pos]
    age = (date.fromisoformat(as_of) - date.fromisoformat(snap)).days
    return dict(status='STALE' if age > max_age_days else 'OBSERVED_ASOF_PARTIAL',
                symbols=sorted(set(snapshots[snap])), snapshot_date=snap, age_days=age,
                strict_pit_ready=False)


def research_dependencies(calendar: list[str], candidates: Mapping[str, list[str]], *,
                          lookback_bars: int, label_sessions: int) -> dict:
    """Include formation for every candidate and all execution/label valuation days."""
    if lookback_bars < 1 or label_sessions < 1:
        raise ValueError('lookback and label sessions must be positive')
    if calendar != sorted(set(calendar)):
        raise ValueError('calendar must be sorted and unique')
    indices = {day: i for i, day in enumerate(calendar)}
    result = {purpose: {} for purpose in ('formation', 'execution', 'label')}
    errors = []
    for day, symbols in sorted(candidates.items()):
        if day not in indices:
            raise ValueError(f'candidate date outside calendar: {day}')
        i = indices[day]
        if i + 1 < lookback_bars:
            errors.append(dict(date=day, reason='INSUFFICIENT_WARMUP', symbols=sorted(set(symbols))))
        if i + 1 >= len(calendar):
            errors.append(dict(date=day, reason='MISSING_EXECUTION_DATE', symbols=sorted(set(symbols))))
        if i + label_sessions >= len(calendar):
            errors.append(dict(date=day, reason='INCOMPLETE_FORWARD_LABEL', symbols=sorted(set(symbols))))
        spans = {'formation': calendar[max(0, i-lookback_bars+1):i+1],
                 'execution': calendar[i+1:i+2], 'label': calendar[i+1:i+label_sessions+1]}
        for purpose, days in spans.items():
            for symbol in set(symbols):
                result[purpose].setdefault(symbol, set()).update(days)
    return {**{purpose: {s: sorted(d) for s, d in sorted(per_symbol.items())}
               for purpose, per_symbol in result.items()}, 'boundary_errors': errors}
