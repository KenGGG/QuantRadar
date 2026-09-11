"""Read-only inventory of reusable material in a pinned base release."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any


_PRICE_FIELDS = {"tradedate", "symbol", "open", "high", "low", "close", "volume", "amount"}


def _entry(*, state: str, selected_table: str | None, reusable_tables: list[str], fields: list[str], stats: dict[str, Any] | None = None, units: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "state": state,
        "selected_table": selected_table,
        "reusable_tables": reusable_tables,
        "fields": fields,
        "coverage": stats or {},
        "units": units or {},
    }


def classify_base_tables(schemas: dict[str, list[str]], stats: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Classify discovered base tables without inferring coverage from table names.

    `final_a_stock_eod_price` is the current price selection.  Other complete
    OHLCV tables remain reusable candidates and are deliberately reported
    rather than discarded as duplicate directories.
    """
    price_tables = [name for name, columns in schemas.items() if _PRICE_FIELDS <= set(columns)]
    final = "final_a_stock_eod_price" if "final_a_stock_eod_price" in price_tables else None
    selected = final or (price_tables[0] if price_tables else None)
    report: dict[str, dict[str, Any]] = {
        "price": _entry(
            state="VALID" if selected else "UNKNOWN",
            selected_table=selected,
            reusable_tables=[name for name in price_tables if name != selected],
            fields=sorted(_PRICE_FIELDS),
            stats=stats.get(selected, {}) if selected else {},
            units={"volume": "hand", "amount": "thousand_yuan"} if selected else {},
        )
    }
    status_table = "bao_a_stock_eod_info" if {"tradedate", "symbol", "tradestatus", "is_st"} <= set(schemas.get("bao_a_stock_eod_info", [])) else None
    report["trade_status"] = _entry(
        state="PARTIAL" if status_table else "UNKNOWN", selected_table=status_table, reusable_tables=[],
        fields=["tradestatus", "is_st", "turn"], stats=stats.get(status_table, {}) if status_table else {},
    )
    lifecycle_table = "ts_a_stock_list" if {"ts_code", "list_date", "delist_date"} <= set(schemas.get("ts_a_stock_list", [])) else None
    report["lifecycle"] = _entry(
        state="PARTIAL" if lifecycle_table else "UNKNOWN", selected_table=lifecycle_table, reusable_tables=[],
        fields=["ts_code", "list_date", "delist_date"], stats=stats.get(lifecycle_table, {}) if lifecycle_table else {},
    )
    calendar_table = "ts_trade_day_calendar" if {"date", "is_open"} <= set(schemas.get("ts_trade_day_calendar", [])) else None
    report["calendar"] = _entry(
        state="VALID" if calendar_table else "UNKNOWN", selected_table=calendar_table, reusable_tables=[],
        fields=["date", "is_open"], stats=stats.get(calendar_table, {}) if calendar_table else {},
    )
    index_table = "ts_index_weight" if {"index_code", "stock_code", "trade_date", "weight"} <= set(schemas.get("ts_index_weight", [])) else None
    report["index_weight"] = _entry(
        state="PARTIAL" if index_table else "UNKNOWN", selected_table=index_table, reusable_tables=[],
        fields=["index_code", "stock_code", "trade_date", "weight"], stats=stats.get(index_table, {}) if index_table else {},
    )
    return report


def scan_base(cursor) -> dict[str, Any]:
    """Discover supported tables and aggregate coverage through one read-only cursor."""
    cursor.execute("SELECT TABLE_NAME AS name FROM information_schema.tables WHERE table_schema=DATABASE() ORDER BY TABLE_NAME")
    tables = [row["name"] for row in cursor.fetchall()]
    schemas: dict[str, list[str]] = {}
    for table in tables:
        cursor.execute(f"SHOW COLUMNS FROM `{table}`")
        schemas[table] = [row["Field"] for row in cursor.fetchall()]
    date_columns = {
        "final_a_stock_eod_price": ("tradedate", "symbol"),
        "ts_a_stock_eod_price": ("tradedate", "symbol"),
        "bao_a_stock_eod_info": ("tradedate", "symbol"),
        "ts_a_stock_list": ("list_date", "ts_code"),
        "ts_trade_day_calendar": ("date", "id"),
        "ts_index_weight": ("trade_date", "stock_code"),
    }
    stats: dict[str, dict[str, Any]] = {}
    for table, (day, symbol) in date_columns.items():
        if table not in schemas or day not in schemas[table] or symbol not in schemas[table]:
            continue
        cursor.execute(f"SELECT MIN(`{day}`) AS first_date, MAX(`{day}`) AS latest_date, COUNT(DISTINCT `{symbol}`) AS stocks, COUNT(*) AS row_count FROM `{table}`")
        stats[table] = {key: str(value)[:10] if key.endswith("date") and value is not None else value for key, value in cursor.fetchone().items()}
    aliases = []
    if "ts_index_weight" in schemas:
        cursor.execute(
            "SELECT a.trade_date AS trade_date FROM "
            "(SELECT DISTINCT trade_date FROM ts_index_weight WHERE index_code='000300.SH') a "
            "JOIN (SELECT DISTINCT trade_date FROM ts_index_weight WHERE index_code='399300.SZ') b "
            "ON a.trade_date=b.trade_date ORDER BY trade_date"
        )
        common_days = [str(row["trade_date"])[:10] for row in cursor.fetchall()]
        samples = []
        for day in common_days:
            cursor.execute("SELECT stock_code FROM ts_index_weight WHERE index_code=%s AND trade_date=%s", ("000300.SH", day))
            left = {row["stock_code"] for row in cursor.fetchall()}
            cursor.execute("SELECT stock_code FROM ts_index_weight WHERE index_code=%s AND trade_date=%s", ("399300.SZ", day))
            right = {row["stock_code"] for row in cursor.fetchall()}
            samples.append((day, left, right))
        aliases.append(validate_index_alias("000300.SH", "399300.SZ", samples))
    return {"tables": schemas, "domains": classify_base_tables(schemas, stats), "index_aliases": aliases}


def validate_index_alias(left_code: str, right_code: str, samples: list[tuple[str, set[str], set[str]]]) -> dict[str, Any]:
    """Approve an index alias only for observed, identical constituent snapshots."""
    if not samples:
        return {"left_code": left_code, "right_code": right_code, "state": "UNKNOWN", "reason": "no overlapping snapshots"}
    dates = [sample[0] for sample in samples]
    mismatches = [day for day, left, right in samples if left != right]
    if mismatches:
        return {"left_code": left_code, "right_code": right_code, "state": "CONFLICT", "effective_from": min(dates), "effective_to": max(dates),
                "checked_snapshots": len(samples), "mismatch_dates": mismatches}
    return {"left_code": left_code, "right_code": right_code, "state": "VALID", "effective_from": min(dates), "effective_to": max(dates),
            "checked_snapshots": len(samples), "relation": "same_constituents_observed"}


def build_gap_plan(domains: dict[str, dict[str, Any]], *, start: str, end: str, requirements: dict[str, str]) -> dict[str, Any]:
    """Make a range-level plan; it never treats a missing table as a network request."""
    strategy_gap = []
    satisfied = []
    for domain, contract in requirements.items():
        detail = domains.get(domain, {})
        coverage = detail.get("coverage", {})
        latest = coverage.get("latest_date")
        if detail.get("state") == "VALID" and coverage.get("first_date", "9999-12-31") <= start and latest and latest >= end:
            satisfied.append(domain)
            continue
        if latest and latest < end:
            next_day = (date.fromisoformat(str(latest)[:10]) + timedelta(days=1)).isoformat()
            gap_start = max(start, next_day)
        else:
            gap_start = start
        strategy_gap.append({"domain": domain, "range": {"start": gap_start, "end": end}, "state": "UNKNOWN", "source_contract_id": contract})
    return {"strategy_window": {"start": start, "end": end}, "satisfied_by_base": satisfied, "strategy_gap": strategy_gap,
            "current_update": [], "historical_repair": []}
