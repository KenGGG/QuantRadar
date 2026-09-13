"""Resumable, raw-backed BaoStock daily candidates for research qualification."""
from __future__ import annotations

import hashlib
import csv
import io
import json
import os
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .adapters import ADAPTER_VERSION, BaostockAdapter, FetchedRows
from .research_inputs import standard_panel
from .sources import normalize_baostock_daily_bundle
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
            receipt = None
            try:
                if not fetched.candidate_domains:
                    raise ValueError("daily source did not provide candidate domains")
                receipt = raw.put(f"stock_daily/{symbol}", fetched.raw_bytes)
                price = fetched.candidate_domains["price"]
                status = fetched.candidate_domains["trade_status"]
                # Even a lightweight adapter must retain the captured response
                # hash rather than an adapter-supplied placeholder.
                for row in [*price, *status]:
                    row["raw_sha256"] = receipt["sha256"]
                    row.setdefault("symbol", symbol)
                wanted = expected_days[symbol]
                price_by_day = {str(row["trade_date"]): row for row in price}
                status_by_day = {str(row["trade_date"]): row for row in status}
                if set(price_by_day) != set(wanted) or set(status_by_day) != set(wanted):
                    raise ValueError("source sessions do not exactly match requested sessions")
                if any(row.get("tradestatus") not in (0, 1) or row.get("is_st") not in (0, 1) for row in status_by_day.values()):
                    raise ValueError("unknown trade status cannot be complete")
                price_complete = not any(
                    any(row.get(field) is None for field in ("open", "high", "low", "close", "volume", "amount"))
                    for row in price_by_day.values()
                )
                panel = standard_panel(pd.DataFrame([price_by_day[day] for day in wanted]), unit_contract="baostock-shares-yuan", adjustment="raw") if price_complete else None
                content = json.dumps(
                    {
                        "symbol": symbol,
                        "requested_sessions": wanted,
                        "raw_sha256": receipt["sha256"],
                        "price": panel.to_dict("records") if panel is not None else [],
                        "trade_status": [status_by_day[day] for day in wanted],
                        "price_qualification": "CANDIDATE_NOT_PUBLISHED" if price_complete else "MISSING_OHLCV_OR_AMOUNT",
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
                    price_qualification="CANDIDATE_NOT_PUBLISHED" if price_complete else "MISSING_OHLCV_OR_AMOUNT",
                )
                completed.append(symbol)
            except Exception as exc:
                details = {"category": "STOCK_DAILY_CANDIDATE_REJECTED"}
                if receipt is not None:
                    details["raw_sha256"] = receipt["sha256"]
                journal.fail(symbol, f"{type(exc).__name__}: {exc}", **details)
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


def price_rows_from_stock_candidates(root: Path | str, symbols: Iterable[str] | None = None) -> list[dict[str, Any]]:
    """Load complete raw-price candidates without treating a placeholder factor as a fact."""
    root = Path(root)
    stage = root / "stock-daily-candidates"
    paths = ([stage / f"{symbol}.json" for symbol in symbols] if symbols is not None else sorted(stage.glob("*.json")))
    rows: list[dict[str, Any]] = []
    for path in paths:
        candidate = json.loads(path.read_text(encoding="utf-8"))
        if candidate.get("qualification") != "CANDIDATE_NOT_PUBLISHED" or candidate.get("price_qualification") != "CANDIDATE_NOT_PUBLISHED":
            raise ValueError(f"price candidate is not qualified: {path.name}")
        for price in candidate.get("price", []):
            if price.get("symbol") != candidate.get("symbol") or price.get("raw_sha256") != candidate.get("raw_sha256"):
                raise ValueError(f"price candidate provenance mismatch: {path.name}")
            row = {key: price.get(key) for key in (
                "trade_date", "symbol", "open", "high", "low", "close", "volume", "amount", "preclose",
                "source", "raw_sha256", "adapter_version", "fetched_at", "available_date", "pit_status",
            )}
            rows.append({**row, "source_contract_id": "baostock-daily-v2", "unit_contract_version": "baostock-shares-yuan"})
    return sorted(rows, key=lambda row: (str(row["trade_date"]), str(row["symbol"])))


def replay_stock_daily_candidates_from_raw(
    root: Path | str,
    symbols: Iterable[str],
    start: str,
    end: str,
    *,
    expected_days: dict[str, list[str]],
    raw_hashes: dict[str, str],
    durable_raw_root: Path | str,
) -> dict[str, Any]:
    """Reparse a captured SDK response after a parser fix, without re-fetching."""
    selected = sorted(set(symbols))
    if set(selected) != set(raw_hashes):
        raise ValueError("symbols and raw hashes must have identical keys")
    raw = RawStore(durable_raw_root)

    class ReplayAdapter:
        def daily_bundles(self, requested, *_args, **_kwargs):
            for symbol in requested:
                digest = raw_hashes[symbol]
                content = raw.read(digest)
                source_rows = list(csv.DictReader(io.StringIO(content.decode("utf-8"))))
                bundle = normalize_baostock_daily_bundle(
                    source_rows,
                    raw_sha256=digest,
                    fetched_at="REPLAYED_FROM_RAW",
                    adapter_version=ADAPTER_VERSION,
                )
                yield symbol, FetchedRows(
                    "trade_status_daily", content, bundle["trade_status"], "baostock", "REPLAYED_FROM_RAW",
                    candidate_domains=bundle, evidence_level="SDK_RESPONSE_SNAPSHOT",
                )

    return collect_stock_daily_candidates(
        root, selected, start, end, expected_days=expected_days,
        adapter=ReplayAdapter(), raw_root=durable_raw_root,
    )
