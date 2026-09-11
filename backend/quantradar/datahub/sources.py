"""Pure normalization for the three DataHub V1 source datasets.

Network clients deliberately live outside these functions.  Normalization is
therefore deterministic, rejects malformed source values, and remains easy to
audit against the raw payload hash stored with every row.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable

import pandas as pd


PIT_PARTIAL = "PARTIAL"


def _date(value: Any, field: str) -> str:
    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} is not a date: {value!r}") from exc
    if pd.isna(parsed):
        raise ValueError(f"{field} is not a date: {value!r}")
    return parsed.strftime("%Y-%m-%d")


def _number(value: Any, field: str) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} is not numeric: {value!r}") from exc
    if pd.isna(result):
        raise ValueError(f"{field} is not numeric: {value!r}")
    return result


def _symbol(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw.startswith("sh.") and len(raw) == 9 and raw[3:].isdigit():
        return f"{raw[3:]}.SH"
    if raw.startswith("sz.") and len(raw) == 9 and raw[3:].isdigit():
        return f"{raw[3:]}.SZ"
    raise ValueError(f"unsupported Shanghai/Shenzhen A-share code: {value!r}")


def _eastmoney_symbol(value: Any) -> str:
    text = str(value or "").strip().upper()
    if len(text) == 9 and text[:6].isdigit() and text[6:] in {".SH", ".SZ"}:
        return text
    raise ValueError(f"unsupported Eastmoney Shanghai/Shenzhen A-share code: {value!r}")


def _six_digit(value: Any, field: str) -> str:
    """Accept Excel's integral numeric cells without corrupting leading zeroes."""
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"{field} is invalid: {value!r}")
        value = int(value)
    text = str(value or "").strip()
    if not text.isdigit() or len(text) > 6:
        raise ValueError(f"{field} is invalid: {value!r}")
    return text.zfill(6)


def normalize_valuation_rows(
    rows: Iterable[dict[str, Any]], *, source: str, raw_sha256: str, fetched_at: str, adapter_version: str = "a-stock-data@2012ce7"
) -> list[dict[str, Any]]:
    """Normalize Baostock daily valuation data without silently coercing errors."""
    result: list[dict[str, Any]] = []
    for raw in rows:
        result.append(
            {
                "trade_date": _date(raw.get("date"), "date"),
                "symbol": _symbol(raw.get("code")),
                "pe_ttm": _number(raw.get("peTTM"), "peTTM"),
                "pb_mrq": _number(raw.get("pbMRQ"), "pbMRQ"),
                "ps_ttm": _number(raw.get("psTTM"), "psTTM"),
                "pcf_ncf_ttm": _number(raw.get("pcfNcfTTM"), "pcfNcfTTM"),
                "source": source,
                "raw_sha256": raw_sha256,
                "adapter_version": adapter_version,
                "fetched_at": fetched_at,
                "available_date": None,
                "pit_status": PIT_PARTIAL,
            }
        )
    return result


def normalize_eastmoney_valuation_rows(
    rows: Iterable[dict[str, Any]], *, raw_sha256: str, fetched_at: str, adapter_version: str
) -> list[dict[str, Any]]:
    """Normalize Eastmoney's date-sliced valuation contract without semantic aliases."""
    result: list[dict[str, Any]] = []
    for raw in rows:
        result.append(
            {
                "trade_date": _date(raw.get("TRADE_DATE"), "TRADE_DATE"),
                "symbol": _eastmoney_symbol(raw.get("SECUCODE")),
                "pe_ttm": _number(raw.get("PE_TTM"), "PE_TTM"),
                "pb_mrq": _number(raw.get("PB_MRQ"), "PB_MRQ"),
                "ps_ttm": _number(raw.get("PS_TTM"), "PS_TTM"),
                "pcf_ocf_ttm": _number(raw.get("PCF_OCF_TTM"), "PCF_OCF_TTM"),
                "source": "eastmoney:RPT_VALUEANALYSIS_DET",
                "raw_sha256": raw_sha256,
                "adapter_version": adapter_version,
                "fetched_at": fetched_at,
                "available_date": None,
                "pit_status": PIT_PARTIAL,
            }
        )
    return sorted(result, key=lambda row: row["symbol"])


def normalize_lifecycle_row(
    raw: dict[str, Any], *, raw_sha256: str, fetched_at: str, adapter_version: str = "a-stock-data@2012ce7"
) -> dict[str, Any]:
    """Normalize a Baostock listing row; current fetch time is not historical availability."""
    status = str(raw.get("status", "")).strip()
    if status not in {"0", "1"}:
        raise ValueError(f"unsupported lifecycle status: {status!r}")
    delist_raw = str(raw.get("outDate") or "").strip()
    return {
        "symbol": _symbol(raw.get("code")),
        "list_date": _date(raw.get("ipoDate"), "ipoDate"),
        "delist_date": _date(delist_raw, "outDate") if delist_raw else None,
        "status": "LISTED" if status == "1" else "DELISTED",
        "source": "baostock",
        "raw_sha256": raw_sha256,
        "adapter_version": adapter_version,
        "fetched_at": fetched_at,
        "available_date": None,
        "pit_status": PIT_PARTIAL,
    }


def lifecycle_active_as_of(row: dict[str, Any], as_of: str) -> bool:
    """Apply known dates only; a later delisting cannot remove an earlier member."""
    day = _date(as_of, "as_of")
    if day < row["list_date"]:
        return False
    return not row.get("delist_date") or day < row["delist_date"]


def build_sw_level_one_intervals(
    rows: Iterable[dict[str, Any]], *, raw_sha256: str, fetched_at: str, adapter_version: str = "a-stock-data@2012ce7"
) -> list[dict[str, Any]]:
    """Turn industry change events into non-overlapping effective-dated L1 intervals."""
    events: dict[str, list[tuple[str, str]]] = {}
    for raw in rows:
        code = _six_digit(raw.get("code"), "code")
        prefix = "SH" if code.startswith(("60", "68", "90")) else "SZ" if code.startswith(("00", "30")) else None
        if prefix is None:
            continue
        symbol = f"{code}.{prefix}"
        industry = _six_digit(raw.get("industry_code"), "industry_code")
        events.setdefault(symbol, []).append((_date(raw.get("start_date"), "start_date"), industry[:2] + "0000"))

    result: list[dict[str, Any]] = []
    for symbol, values in events.items():
        values.sort()
        deduplicated: list[tuple[str, str]] = []
        for effective_from, industry_code in values:
            if deduplicated and effective_from == deduplicated[-1][0]:
                if industry_code != deduplicated[-1][1]:
                    raise ValueError(f"conflicting industry assignments for {symbol} on {effective_from}")
                continue
            deduplicated.append((effective_from, industry_code))
        for index, (effective_from, industry_code) in enumerate(deduplicated):
            following = deduplicated[index + 1][0] if index + 1 < len(deduplicated) else None
            effective_to = None
            if following:
                effective_to = (pd.Timestamp(following).date() - timedelta(days=1)).isoformat()
            result.append(
                {
                    "symbol": symbol,
                    "industry_code": industry_code,
                    "effective_from": effective_from,
                    "effective_to": effective_to,
                    "source": "swsresearch",
                    "raw_sha256": raw_sha256,
                    "adapter_version": adapter_version,
                    "fetched_at": fetched_at,
                    "available_date": None,
                    "pit_status": PIT_PARTIAL,
                }
            )
    return sorted(result, key=lambda row: (row["symbol"], row["effective_from"]))
