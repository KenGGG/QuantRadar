from __future__ import annotations

from typing import Any


TABLE_SPECS: dict[str, dict[str, Any]] = {
    "final_a_stock_eod_price": {
        "date_column": "tradedate",
        "key_columns": ("symbol", "tradedate"),
    },
    "bao_a_stock_eod_info": {
        "date_column": "tradedate",
        "key_columns": ("symbol", "tradedate"),
    },
    "final_a_stock_limit": {
        "date_column": "tradedate",
        "key_columns": ("symbol", "tradedate"),
    },
    "ts_index_weight": {
        "date_column": "trade_date",
        "key_columns": ("index_code", "stock_code", "trade_date"),
    },
    "ts_trade_day_calendar": {
        "date_column": "date",
        "key_columns": ("exchange", "date"),
    },
    "ts_a_stock_list": {
        "date_column": "list_date",
        "key_columns": ("ts_code",),
    },
}


_COVERAGE_FIELDS = (
    ("price", "final_a_stock_eod_price", "tradedate", None),
    ("index_constituents", "ts_index_weight", "trade_date", "index_code = '000300.SH'"),
    ("up_down_limits", "final_a_stock_limit", "tradedate", None),
    ("st", "bao_a_stock_eod_info", "tradedate", "is_st IS NOT NULL"),
    ("tradestatus_paused", "bao_a_stock_eod_info", "tradedate", "tradestatus IS NOT NULL"),
    (
        "corporate_action_proxy",
        "bao_a_stock_eod_info",
        "tradedate",
        "adjfactor IS NOT NULL AND preclose IS NOT NULL",
    ),
    ("stock_master", "ts_a_stock_list", "list_date", None),
    ("trade_calendar", "ts_trade_day_calendar", "date", "is_open = 1"),
)


def unique_index_covers(indexes: list[dict[str, Any]], key_columns: tuple[str, ...]) -> bool:
    unique_indexes: dict[str, list[tuple[int, str]]] = {}
    for row in indexes:
        if int(row.get("Non_unique", 1)) != 0:
            continue
        unique_indexes.setdefault(str(row["Key_name"]), []).append(
            (int(row["Seq_in_index"]), str(row["Column_name"]))
        )
    expected = set(key_columns)
    return any(
        {column for _, column in sorted(columns)} == expected
        for columns in unique_indexes.values()
    )


def audit_schema_and_coverage(connection) -> dict[str, Any]:
    """Inspect the PRD tables without assuming their column names or freshness."""
    schemas: dict[str, list[dict[str, Any]]] = {}
    table_summaries: list[dict[str, Any]] = []
    for table, spec in TABLE_SPECS.items():
        columns = connection.query(f"DESCRIBE {table}")
        schemas[table] = [
            {
                "name": row.get("Field"),
                "type": row.get("Type"),
                "nullable": row.get("Null"),
                "key": row.get("Key"),
            }
            for row in columns
        ]
        date_column = spec["date_column"]
        coverage = connection.query_one(
            f"SELECT MIN({date_column}) min_date, MAX({date_column}) max_date, "
            f"COUNT(*) row_count FROM {table}"
        ) or {}
        indexes = connection.query(f"SHOW INDEX FROM {table}")
        unique_enforced = unique_index_covers(indexes, spec["key_columns"])
        table_summaries.append(
            {
                "table": table,
                "date_column": date_column,
                "min_date": coverage.get("min_date"),
                "max_date": coverage.get("max_date"),
                "row_count": coverage.get("row_count", 0),
                "duplicate_groups": 0 if unique_enforced else None,
                "duplicate_check": (
                    "ENFORCED_UNIQUE_INDEX" if unique_enforced else "NO_MATCHING_UNIQUE_INDEX"
                ),
            }
        )

    logical_coverage: list[dict[str, Any]] = []
    for dataset, table, date_column, condition in _COVERAGE_FIELDS:
        where = f" WHERE {condition}" if condition else ""
        row = connection.query_one(
            f"SELECT MIN({date_column}) min_date, MAX({date_column}) max_date, "
            f"COUNT(*) row_count FROM {table}{where}"
        ) or {}
        logical_coverage.append(
            {
                "dataset": dataset,
                "table": table,
                "date_column": date_column,
                "min_date": row.get("min_date"),
                "max_date": row.get("max_date"),
                "row_count": row.get("row_count", 0),
            }
        )

    return {
        "schemas": schemas,
        "table_summaries": table_summaries,
        "coverage": logical_coverage,
    }
