"""Deterministic raw-price resolver for a fixed base release.

This layer deliberately knows nothing about adjusted prices.  It chooses final
rows first and uses BaoStock rows only for absent *raw* keys, carrying the
source and repair reason into every resolved observation.
"""
from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


RAW_FIELDS = ("open", "high", "low", "close", "volume", "amount")


def resolve_raw_price(final: pd.DataFrame, bao: pd.DataFrame, *, symbol: str) -> pd.DataFrame:
    """Resolve ``final -> bao`` raw rows without mixing adjustment anchors.

    ``final`` is expressed in its stored hands/thousand-yuan contract; ``bao``
    is shares/yuan.  The result is always shares/yuan, and has a source marker
    for each row.  A Bao row is eligible only when final has no row for that
    date, never merely because a final field is null.
    """
    _validate_input(final, "final")
    _validate_input(bao, "bao")
    final = final.copy()
    bao = bao.copy()
    final.index = pd.to_datetime(final.index).normalize()
    bao.index = pd.to_datetime(bao.index).normalize()
    if final.index.has_duplicates or bao.index.has_duplicates:
        raise ValueError("raw price source has duplicate dates")

    final["volume"] = final["volume"] * 100.0
    final["amount"] = final["amount"] * 1000.0
    rows = []
    for day in final.index.union(bao.index).sort_values():
        if day in final.index:
            row = final.loc[day, list(RAW_FIELDS)].to_dict()
            source_table, repair = "final_a_stock_eod_price", None
        else:
            row = bao.loc[day, list(RAW_FIELDS)].to_dict()
            _validate_row(row, day)
            source_table, repair = "bao_a_stock_eod_info", "FINAL_ROW_MISSING"
        rows.append({"trade_date": day.strftime("%Y-%m-%d"), "security_id": symbol,
                     **{field: float(row[field]) for field in RAW_FIELDS},
                     "source_table": source_table, "repair_reason": repair,
                     "price_mode": "RAW", "corporate_action_adjusted": False})
    return pd.DataFrame(rows)


def raw_price_readiness(rows: Iterable[dict]) -> dict:
    """Workflow-specific qualification; adjusted/account eligibility is separate."""
    materialized = list(rows)
    complete = bool(materialized) and all(
        all(row.get(field) is not None and np.isfinite(float(row[field])) for field in RAW_FIELDS)
        for row in materialized
    )
    return {"raw_price_ready": complete, "adjusted_price_ready": False,
            "corporate_action_ready": False, "account_replay_ready": False,
            "price_mode": "RAW"}


def _validate_input(frame: pd.DataFrame, source: str) -> None:
    missing = set(RAW_FIELDS) - set(frame.columns)
    if missing:
        raise ValueError(f"{source} raw price fields missing: {sorted(missing)}")


def _validate_row(row: dict, day) -> None:
    values = {key: float(row[key]) for key in RAW_FIELDS}
    if not all(np.isfinite(value) and value >= 0 for value in values.values()):
        raise ValueError(f"invalid Bao raw price on {day:%Y-%m-%d}")
    if values["low"] > min(values["open"], values["close"]) or values["high"] < max(values["open"], values["close"]):
        raise ValueError(f"invalid Bao OHLC bounds on {day:%Y-%m-%d}")
