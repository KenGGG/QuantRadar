"""Turn audited field gaps into exact serial BaoStock bundle requests."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable


BAOSTOCK_BUNDLE_FIELDS = frozenset({"open", "high", "low", "close", "volume", "amount", "tradestatus", "is_st"})


def build_stock_bundle_fetch_plan(runs: Iterable[dict[str, Any]], sessions: list[str]) -> dict[str, Any]:
    """Coalesce only FETCH gaps into session-contiguous, source-sized requests."""
    if sessions != sorted(set(sessions)):
        raise ValueError("sessions must be sorted and unique")
    positions = {day: index for index, day in enumerate(sessions)}
    wanted: dict[str, set[int]] = defaultdict(set)
    fields_by_symbol: dict[str, set[str]] = defaultdict(set)
    ignored = 0
    for run in runs:
        if run.get("action") != "FETCH" or run.get("field") not in BAOSTOCK_BUNDLE_FIELDS:
            ignored += 1
            continue
        symbol = str(run.get("symbol") or "")
        start, end = str(run.get("start_date") or ""), str(run.get("end_date") or "")
        if not symbol or start not in positions or end not in positions or positions[start] > positions[end]:
            raise ValueError("fetch run has an invalid session boundary")
        wanted[symbol].update(range(positions[start], positions[end] + 1))
        fields_by_symbol[symbol].add(str(run["field"]))
    by_range: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for symbol, indexes in wanted.items():
        ordered = sorted(indexes)
        block_start = prior = ordered[0]
        for current in ordered[1:] + [None]:
            if current is not None and current == prior + 1:
                prior = current
                continue
            start, end = sessions[block_start], sessions[prior]
            by_range[(start, end)].append(
                {"symbol": symbol, "expected_sessions": sessions[block_start : prior + 1], "fields": sorted(fields_by_symbol[symbol])}
            )
            if current is not None:
                block_start = prior = current
    tasks = [
        {"start_date": start, "end_date": end, "symbols": sorted(items, key=lambda row: row["symbol"])}
        for (start, end), items in sorted(by_range.items())
    ]
    return {
        "status": "PLANNED_NOT_COLLECTED",
        "source": "baostock",
        "contract": "baostock-daily-v2",
        "task_count": len(tasks),
        "symbol_count": len(wanted),
        "session_count": sum(len(item["expected_sessions"]) for task in tasks for item in task["symbols"]),
        "ignored_nonbundle_runs": ignored,
        "tasks": tasks,
    }
