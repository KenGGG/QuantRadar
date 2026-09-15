"""Release-pinned, field-level coverage accounting without source side effects."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable


@dataclass(frozen=True)
class ExpectedKey:
    symbol: str
    trade_date: str
    fields: tuple[str, ...]
    applicable: bool = True


class CoverageService:
    """Compare an explicit expected-key contract to already published facts.

    Callers determine applicability from a versioned source contract.  This
    class deliberately neither downloads data nor guesses that a missing row
    represents a normal trading state.
    """

    def __init__(self, expected_key_contract: str) -> None:
        if not expected_key_contract:
            raise ValueError("expected_key_contract is required")
        self.expected_key_contract = expected_key_contract

    def audit(self, *, expected: Iterable[dict[str, Any]], actual: Iterable[dict[str, Any]]) -> dict[str, Any]:
        published = {
            (str(row.get("symbol")), str(row.get("trade_date"))[:10]): row
            for row in actual
        }
        missing_dates: dict[tuple[str, str], list[tuple[int, str]]] = defaultdict(list)
        expected_fields = valid_fields = 0
        for position, item in enumerate(expected):
            if not item.get("applicable", True):
                continue
            symbol, trade_date = str(item["symbol"]), str(item["trade_date"])[:10]
            row = published.get((symbol, trade_date), {})
            for field in item["fields"]:
                expected_fields += 1
                if row.get(field) is not None:
                    valid_fields += 1
                else:
                    missing_dates[(symbol, str(field))].append((position, trade_date))
        missing = []
        for (symbol, field), dates in sorted(missing_dates.items()):
            start = previous = None
            for position, day in dates:
                if start is not None and position != previous[0] + 1:
                    missing.append({"symbol": symbol, "field": field, "start": start[1], "end": previous[1],
                                    "expected_key_contract": self.expected_key_contract})
                    start = None
                if start is None:
                    start = (position, day)
                previous = (position, day)
            missing.append({"symbol": symbol, "field": field, "start": start[1], "end": previous[1],
                            "expected_key_contract": self.expected_key_contract})
        return {"expected_key_contract": self.expected_key_contract,
                "expected_fields": expected_fields, "valid_fields": valid_fields,
                "missing_fields": expected_fields - valid_fields, "missing": missing}

    def reaudit_work_order(self, work_order: dict[str, Any], *, expected: Iterable[dict[str, Any]],
                           actual: Iterable[dict[str, Any]]) -> dict[str, Any]:
        """Turn a claimed task into an evidence-backed no-op or residual job."""
        if work_order.get("expected_key_contract") not in (None, self.expected_key_contract):
            return {"status": "OBSOLETE", "evidence": {"reason": "expected key contract changed"}}
        report = self.audit(expected=expected, actual=actual)
        digest = hashlib.sha256(json.dumps(report["missing"], sort_keys=True).encode()).hexdigest()
        return {"status": "SATISFIED" if not report["missing"] else "PENDING",
                "coverage": report,
                "evidence": {"remaining_gap_fingerprint": digest,
                             "expected_key_contract": self.expected_key_contract}}
