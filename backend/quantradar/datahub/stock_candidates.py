"""Resumable, raw-backed BaoStock daily candidates for research qualification."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .adapters import BaostockAdapter
from .research_inputs import standard_panel
from .store import RawStore, UpdateJournal


def collect_stock_daily_candidates(
    root: Path | str,
    symbols: Iterable[str],
    start: str,
    end: str,
    *,
    expected_days: dict[str, list[str]],
    adapter: Any | None = None,
    raw_root: Path | str | None = None,
) -> dict[str, Any]:
    """Capture exact requested sessions; completion is never inferred from rows.

    This stages research candidates only.  It does not write a Dolt fact table
    or make any statement that the current fetch was historically available.
    """
    root = Path(root)
    selected = sorted(set(symbols))
    if not selected or set(selected) != set(expected_days):
        raise ValueError("symbols and expected_days must have the same non-empty keys")
    if any(not days or days != sorted(set(days)) for days in expected_days.values()):
        raise ValueError("expected sessions must be sorted, unique and non-empty")
    journal = UpdateJournal(root / "journals" / "stock-daily-candidates.json")
    raw = RawStore(raw_root or root / "raw-artifacts")
    stage = root / "stock-daily-candidates"
    journal.start("stock-daily-candidates", dataset="stock_daily_candidate")
    journal.ensure_pending(selected, reason="exact research-session daily OHLC/status candidate")
    todo = [symbol for symbol in selected if journal.data["units"].get(symbol, {}).get("status") != "COMPLETE"]
    if not todo:
        return {"status": "COMPLETE", "completed": selected, "remaining": []}
    client = adapter or BaostockAdapter()
    completed: list[str] = []
    failed: dict[str, str] = {}
    try:
        for symbol, fetched in client.daily_bundles(todo, start, end, extended=True):
            journal.running(symbol)
            try:
                if not fetched.candidate_domains:
                    raise ValueError("daily source did not provide candidate domains")
                receipt = raw.put(f"stock_daily/{symbol}", fetched.raw_bytes)
                price = fetched.candidate_domains["price"]
                status = fetched.candidate_domains["trade_status"]
                wanted = expected_days[symbol]
                price_by_day = {str(row["trade_date"]): row for row in price}
                status_by_day = {str(row["trade_date"]): row for row in status}
                if set(price_by_day) != set(wanted) or set(status_by_day) != set(wanted):
                    raise ValueError("source sessions do not exactly match requested sessions")
                if any(any(row.get(field) is None for field in ("open", "high", "low", "close", "volume", "amount")) for row in price_by_day.values()):
                    raise ValueError("missing required OHLCV/amount candidate field")
                if any(row.get("tradestatus") not in (0, 1) or row.get("is_st") not in (0, 1) for row in status_by_day.values()):
                    raise ValueError("unknown trade status cannot be complete")
                panel = standard_panel(pd.DataFrame([price_by_day[day] for day in wanted]), unit_contract="baostock-shares-yuan", adjustment="raw")
                content = json.dumps(
                    {
                        "symbol": symbol,
                        "requested_sessions": wanted,
                        "raw_sha256": receipt["sha256"],
                        "price": panel.to_dict("records"),
                        "trade_status": [status_by_day[day] for day in wanted],
                        "qualification": "CANDIDATE_NOT_PUBLISHED",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                ).encode()
                stage.mkdir(parents=True, exist_ok=True)
                temporary = stage / f"{symbol}.tmp"
                target = stage / f"{symbol}.json"
                temporary.write_bytes(content)
                os.replace(temporary, target)
                journal.complete(
                    symbol,
                    raw_sha256=receipt["sha256"],
                    row_count=len(wanted),
                    staged_result_sha256=hashlib.sha256(content).hexdigest(),
                    source="baostock",
                    adapter_version=price[0]["adapter_version"],
                    evidence_level=fetched.evidence_level,
                    qualification="CANDIDATE_NOT_PUBLISHED",
                )
                completed.append(symbol)
            except Exception as exc:
                journal.fail(symbol, f"{type(exc).__name__}: {exc}", category="STOCK_DAILY_CANDIDATE_REJECTED")
                failed[symbol] = str(exc)
    except Exception as exc:
        return {"status": "PARTIAL", "completed": completed, "failed": failed, "error": str(exc), "remaining": [s for s in todo if s not in completed and s not in failed]}
    return {"status": "COMPLETE" if not failed else "PARTIAL", "completed": completed, "failed": failed, "remaining": [s for s in todo if s not in completed and s not in failed]}


def promote_stock_candidate_raw(root: Path | str, durable_raw_root: Path | str) -> dict[str, Any]:
    """Copy previously captured bytes into the release RawStore with hash checks."""
    root = Path(root)
    source = RawStore(root / "raw-artifacts")
    durable = RawStore(durable_raw_root)
    journal = UpdateJournal(root / "journals" / "stock-daily-candidates.json")
    promoted: list[str] = []
    for symbol, unit in sorted(journal.data.get("units", {}).items()):
        if unit.get("status") != "COMPLETE":
            continue
        digest = str(unit.get("raw_sha256") or "")
        content = source.read(digest)
        receipt = durable.put(f"stock_daily/{symbol}", content)
        if receipt["sha256"] != digest:
            raise ValueError(f"raw hash changed during promotion: {symbol}")
        promoted.append(symbol)
    if not promoted:
        raise ValueError("no completed candidate receipts to promote")
    return {"status": "PROMOTED_NOT_PUBLISHED", "symbols": promoted}
