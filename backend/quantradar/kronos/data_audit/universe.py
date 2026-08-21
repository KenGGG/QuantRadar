from __future__ import annotations

import datetime as dt
from typing import Any, TypeVar

from quantradar.providers.investment_data.symbols import to_joinquant_symbol

from .models import GateEvidence


T = TypeVar("T")


def last_trading_day_per_week(days: list[dt.date]) -> list[dt.date]:
    weeks: dict[tuple[int, int], dt.date] = {}
    for day in sorted(days):
        iso = day.isocalendar()
        weeks[(iso.year, iso.week)] = day
    return list(weeks.values())


def select_evenly(values: list[T], count: int) -> list[T]:
    if count <= 0 or not values:
        return []
    if len(values) <= count:
        return list(values)
    if count == 1:
        return [values[0]]
    indexes = [int(index * (len(values) - 1) / (count - 1)) for index in range(count)]
    return [values[index] for index in indexes]


def select_auditable_weeks(
    days: list[dt.date],
    *,
    first_snapshot: dt.date,
    last_snapshot: dt.date,
    count: int,
) -> list[dt.date]:
    weekly = last_trading_day_per_week(days)
    covered = [day for day in weekly if first_snapshot <= day <= last_snapshot]
    return select_evenly(covered, count)


def audit_pit_universe(connection, provider, min_weeks: int = 20) -> dict[str, Any]:
    snapshot_range = connection.query_one(
        "SELECT MIN(trade_date) min_date, MAX(trade_date) max_date "
        "FROM ts_index_weight WHERE index_code = %s",
        ("000300.SH",),
    ) or {}
    first_snapshot = snapshot_range.get("min_date")
    last_snapshot = snapshot_range.get("max_date")
    if first_snapshot is None or last_snapshot is None:
        return {
            "rows": [],
            "evidence": GateEvidence.blocked(
                "No 000300.SH historical snapshots are available",
                "pit_universe_checks.csv",
            ),
        }
    calendar_rows = connection.query(
        "SELECT date FROM ts_trade_day_calendar WHERE is_open = 1 "
        "AND date BETWEEN %s AND %s ORDER BY date",
        (first_snapshot, last_snapshot),
    )
    days = [row["date"] for row in calendar_rows]
    audit_dates = select_auditable_weeks(
        days,
        first_snapshot=first_snapshot,
        last_snapshot=last_snapshot,
        count=min_weeks,
    )
    results: list[dict[str, Any]] = []
    for audit_date in audit_dates:
        snapshot = connection.query_one(
            "SELECT MAX(trade_date) snapshot_date FROM ts_index_weight "
            "WHERE index_code = %s AND trade_date <= %s",
            ("000300.SH", audit_date),
        ) or {}
        snapshot_date = snapshot.get("snapshot_date")
        source_rows = (
            connection.query(
                "SELECT stock_code FROM ts_index_weight WHERE index_code = %s "
                "AND trade_date = %s ORDER BY stock_code",
                ("000300.SH", snapshot_date),
            )
            if snapshot_date is not None
            else []
        )
        source = {to_joinquant_symbol(row["stock_code"]) for row in source_rows}
        actual = set(provider.get_index_stocks("000300.XSHG", audit_date))
        missing = sorted(source - actual)
        extra = sorted(actual - source)
        results.append(
            {
                "audit_date": audit_date,
                "snapshot_date": snapshot_date,
                "snapshot_lag_days": (
                    (audit_date - snapshot_date).days if snapshot_date is not None else None
                ),
                "snapshot_not_future": snapshot_date is not None and snapshot_date <= audit_date,
                "expected_count": len(source),
                "provider_count": len(actual),
                "missing_count": len(missing),
                "extra_count": len(extra),
                "missing_symbols": ";".join(missing),
                "extra_symbols": ";".join(extra),
                "status": (
                    "PASS"
                    if snapshot_date is not None
                    and snapshot_date <= audit_date
                    and not missing
                    and not extra
                    else "FAIL"
                ),
            }
        )
    failures = [row for row in results if row["status"] != "PASS"]
    if len(results) < min_weeks:
        evidence = GateEvidence.blocked(
            f"Only {len(results)} of {min_weeks} required PIT weeks were available",
            "pit_universe_checks.csv",
        )
    elif failures:
        evidence = GateEvidence.fail(
            f"{len(failures)} PIT universe checks disagreed with their historical snapshots",
            "pit_universe_checks.csv",
        )
    else:
        evidence = GateEvidence.pass_("pit_universe_checks.csv")
    return {"rows": results, "evidence": evidence}
