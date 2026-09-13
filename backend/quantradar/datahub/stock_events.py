"""Governed Cninfo implementation-announcement candidates for A-share events.

The source response is retained as HTTP raw bytes.  Parsed facts are deliberately
only candidates: the source has no verified historical publication timestamp and
an omitted ratio is never silently converted to zero.
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
import math
import re
from typing import Any

from .research_collection import GovernedHttpSource

CNINFO_DIVIDEND_URL = "https://webapi.cninfo.com.cn/api/sysapi/p_sysapi1139"
CNINFO_CONTRACT = "akshare-cninfo-dividend-http-v1"


def _day(value: Any) -> str | None:
    text = str(value or "").strip()[:10]
    if not text or text in {"--", "---"}:
        return None
    return date.fromisoformat(text).isoformat()


def _number(value: Any, field: str) -> float | None:
    if value in (None, "", "--", "---"):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid Cninfo {field}: {value!r}") from exc
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"invalid Cninfo {field}: {value!r}")
    return result


def parse_cninfo_dividend(content: bytes, *, symbol: str) -> list[dict[str, Any]]:
    """Parse raw Cninfo rows without guessing absent cash or share ratios."""
    if not re.fullmatch(r"(?:00|30|60|68)\d{4}", symbol):
        raise ValueError("A-share six-digit symbol is required")
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid Cninfo JSON") from exc
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("Cninfo response lacks records list")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in records:
        if not isinstance(raw, dict):
            raise ValueError("Cninfo event row is not an object")
        implementation_announcement_date = _day(raw.get("F006D"))
        if implementation_announcement_date is None:
            raise ValueError("Cninfo implementation announcement date is required")
        bonus_per_ten = _number(raw.get("F010N"), "bonus ratio")
        capitalization_per_ten = _number(raw.get("F011N"), "capitalization ratio")
        cash_per_ten = _number(raw.get("F012N"), "cash ratio")
        # A ratio is a source value only when present.  Multiplier needs both
        # share components, so an omitted component remains unresolved.
        share_multiplier = None
        if bonus_per_ten is not None and capitalization_per_ten is not None:
            share_multiplier = 1.0 + (bonus_per_ten + capitalization_per_ten) / 10.0
        canonical = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        event_id = hashlib.sha256(f"{symbol}:{canonical}".encode()).hexdigest()
        if event_id in seen:
            raise ValueError("duplicate Cninfo event row")
        seen.add(event_id)
        result.append(
            {
                "event_id": event_id,
                "symbol": symbol,
                "implementation_announcement_date": implementation_announcement_date,
                "action_type": str(raw.get("F044V") or "").strip() or None,
                "cash_per_ten": cash_per_ten,
                "cash_per_share": cash_per_ten / 10.0 if cash_per_ten is not None else None,
                "bonus_shares_per_ten": bonus_per_ten,
                "capitalization_shares_per_ten": capitalization_per_ten,
                "share_multiplier": share_multiplier,
                "record_date": _day(raw.get("F018D")),
                "ex_date": _day(raw.get("F020D")),
                "cash_payment_date": _day(raw.get("F023D")),
                "share_arrival_date": _day(raw.get("F025D")),
                "plan_text": str(raw.get("F007V") or "").strip() or None,
                # Cninfo's source label is a report period (for example
                # ``2025年报``), not consistently an ISO publication date.
                "report_period": str(raw.get("F001V") or "").strip() or None,
                "source_contract_id": CNINFO_CONTRACT,
                "evidence_level": "HTTP_RAW",
                "available_date": implementation_announcement_date,
                "pit_status": "PARTIAL",
                "qualification": "IMPLEMENTATION_ANNOUNCEMENT_CANDIDATE",
            }
        )
    return sorted(result, key=lambda row: (row["implementation_announcement_date"], row["event_id"]))


class CninfoDividendAdapter:
    """Use AKShare's reviewed request authentication with governed HTTP capture."""

    def __init__(self, transport: GovernedHttpSource) -> None:
        if transport.endpoint != "cninfo-dividend":
            raise ValueError("Cninfo transport endpoint is required")
        self.transport = transport

    @staticmethod
    def _headers() -> dict[str, str]:
        # This reproduces the installed AKShare 1.18.94 request contract while
        # keeping bytes, response headers and failures in our own journal.
        from akshare.stock.stock_dividend_cninfo import _get_file_content_ths
        from py_mini_racer import py_mini_racer

        runtime = py_mini_racer.MiniRacer()
        runtime.eval(_get_file_content_ths("cninfo.js"))
        return {
            "Accept": "*/*",
            "Accept-Enckey": runtime.call("getResCode1"),
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Origin": "http://webapi.cninfo.com.cn",
            "Referer": "http://webapi.cninfo.com.cn/",
            "User-Agent": "QuantRadar DataHub/2",
            "X-Requested-With": "XMLHttpRequest",
        }

    def events(self, symbol: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if not re.fullmatch(r"(?:00|30|60|68)\d{4}", symbol):
            raise ValueError("A-share six-digit symbol is required")
        receipt = self.transport.fetch(
            CNINFO_DIVIDEND_URL,
            {"scode": symbol},
            method="POST",
            headers=self._headers(),
            contract=CNINFO_CONTRACT,
        )
        return receipt, parse_cninfo_dividend(receipt["content"], symbol=symbol)
