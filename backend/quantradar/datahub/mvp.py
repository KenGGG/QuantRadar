"""Resumable per-shard staging for the partial-ingestion MVP."""
from __future__ import annotations

import hashlib
import json
import os
import signal
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from .store import RawStore, UpdateJournal
from .governor import CircuitOpen, RequestGovernor


@dataclass(frozen=True)
class FetchedShard:
    rows: list[dict]
    raw_bytes: bytes
    raw_sha256: str


class AdapterParseError(RuntimeError):
    """A per-symbol public-SDK parsing failure, never evidence of a source outage."""

    def __init__(self, *, symbol: str, function: str, adapter_version: str, exception: Exception, started_at: str, finished_at: str) -> None:
        self.symbol, self.function, self.adapter_version = symbol, function, adapter_version
        self.exception_type, self.raw_status = type(exception).__name__, "UNAVAILABLE_SDK_EXCEPTION"
        self.request_started_at, self.request_finished_at = started_at, finished_at
        super().__init__(f"{symbol} {function}: {type(exception).__name__}: {exception}")

    def metadata(self) -> dict[str, str]:
        return {"symbol": self.symbol, "category": "SYMBOL_DATA_ERROR", "exception_type": self.exception_type, "exception_message": str(self),
                "adapter": self.function, "adapter_version": self.adapter_version,
                "request_started_at": self.request_started_at, "request_finished_at": self.request_finished_at,
                "raw_status": self.raw_status}


class AkshareValuationFetcher:
    """One official AKShare SDK call per symbol; no DataHub outer retry."""
    def __init__(self, governor: RequestGovernor, api=None) -> None:
        self.governor = governor
        if api is None:
            import akshare as ak
            api = ak.stock_value_em
        self.api = api

    def __call__(self, symbol: str) -> FetchedShard | None:
        code = symbol.split(".")[0]
        started_at = datetime.now(timezone.utc).isoformat()
        def request():
            try:
                frame = self.api(code)
                if frame is None:
                    raise TypeError("AKShare returned None")
                _ = frame.empty, frame.columns
                return frame
            except (TypeError, KeyError, AttributeError) as exc:
                raise AdapterParseError(symbol=symbol, function="akshare.stock_value_em", adapter_version="akshare-1.18.94",
                                        exception=exc, started_at=started_at, finished_at=datetime.now(timezone.utc).isoformat()) from exc
        frame = self.governor.call(f"valuation_daily/{code}", request, max_attempts=2, http_attempts_known=False)
        if frame.empty:
            return []
        raw_bytes = frame.to_csv(index=False).encode("utf-8")
        raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        fetched_at = datetime.now(timezone.utc).isoformat()
        required = {"数据日期", "PE(TTM)", "市净率", "市销率", "市现率"}
        missing = required - set(frame.columns)
        if missing:
            raise AdapterParseError(symbol=symbol, function="akshare.stock_value_em", adapter_version="akshare-1.18.94",
                                    exception=RuntimeError(f"missing columns: {sorted(missing)}"), started_at=started_at,
                                    finished_at=datetime.now(timezone.utc).isoformat())
        rows = []
        for source in frame.to_dict("records"):
            day = str(source["数据日期"])
            rows.append({
                "trade_date": day[:10], "symbol": symbol, "pe_ttm": _number(source["PE(TTM)"]),
                "pb_mrq": _number(source["市净率"]), "ps_ttm": _number(source["市销率"]),
                "pcf_ocf_ttm": _number(source["市现率"]), "source": "eastmoney:RPT_VALUEANALYSIS_DET",
                "raw_sha256": raw_sha256, "adapter_version": "akshare-1.18.94", "fetched_at": fetched_at,
                "available_date": None, "pit_status": "PARTIAL",
            })
        return FetchedShard(rows, raw_bytes, raw_sha256)


def _number(value):
    if value is None or str(value).lower() == "nan":
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('non-finite valuation')
    return result


class ShardRunner:
    def __init__(self, stage_root: Path | str, journal: UpdateJournal, fetch: Callable[[str], list[dict] | None], raw_store: RawStore | None = None) -> None:
        self.stage_root, self.journal, self.fetch, self.raw_store = Path(stage_root), journal, fetch, raw_store
        self.stop_requested = False

    def request_stop(self, *_args) -> None:
        self.stop_requested = True

    def run(self, symbols: Iterable[str], *, resume: bool = True, limit: int = 0, target_as_of: str | None = None, requested_start: str | None = None) -> dict:
        self.journal.start(self.journal.data.get("operation_id") or "valuation-mvp", dataset="valuation_daily")
        selected = list(symbols)
        if limit: selected = selected[:limit]
        previous_int, previous_term = signal.getsignal(signal.SIGINT), signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGINT, self.request_stop)
        signal.signal(signal.SIGTERM, self.request_stop)
        for symbol in selected:
            # A WebUI/API control update is another process; reload before
            # accepting the next shard so the current atomic write can finish.
            self.journal.data = self.journal._load()
            if self.journal.paused():
                self.stop_requested = True
            if self.stop_requested:
                self.journal.heartbeat(phase="download", current_shard=None, pid=os.getpid())
                self.journal.phase("download", "PAUSED")
                break
            if resume and self.journal.data["units"].get(symbol, {}).get("status") in {"COMPLETE", "LEGAL_EMPTY", "NOT_COVERED", "FAILED"}:
                continue
            self.journal.running(symbol)
            self.journal.heartbeat(phase="download", current_shard=symbol, pid=os.getpid())
            try:
                fetched = self.fetch(symbol)
                rows = fetched.rows if isinstance(fetched, FetchedShard) else fetched
                if rows is None:
                    self.journal.fail(symbol, "Empty response without coverage evidence", category="UNKNOWN_EMPTY")
                    continue
                if not rows:
                    self.journal.fail(symbol, "Empty response without coverage evidence", category="UNKNOWN_EMPTY")
                    continue
                content = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows).encode()
                digest = fetched.raw_sha256 if isinstance(fetched, FetchedShard) else hashlib.sha256(content).hexdigest()
                receipt = None
                if isinstance(fetched, FetchedShard) and self.raw_store is not None:
                    receipt = self.raw_store.put(f"valuation_daily/{symbol}", fetched.raw_bytes)
                    if receipt["sha256"] != digest:
                        raise RuntimeError("persisted raw hash does not match normalized shard")
                path = self.stage_root / "valuation_daily" / f"{symbol}.jsonl"
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_suffix(".tmp")
                temporary.write_bytes(content); os.replace(temporary, path)
                first_date = min(str(row.get("trade_date")) for row in rows)
                last_date = max(str(row.get("trade_date")) for row in rows)
                self.journal.complete(symbol, raw_sha256=digest, row_count=len(rows),
                                      source=rows[0].get("source"), adapter_version=rows[0].get("adapter_version"),
                                      fetched_at=rows[0].get("fetched_at"), first_date=first_date, last_date=last_date,
                                      target_as_of=target_as_of, last_checked_target=target_as_of,
                                      requested_start=requested_start,
                                      raw_bytes=receipt["bytes"] if receipt else len(content))
                self.journal.data['units'][symbol]['staged_result_sha256'] = hashlib.sha256(content).hexdigest()
                self.journal._save()
                self.journal.heartbeat(phase="download", current_shard=None, pid=os.getpid())
            except Exception as exc:
                if isinstance(exc, CircuitOpen):
                    self.journal.pending(symbol, str(exc))
                    self.journal.heartbeat(phase="download", current_shard=None, pid=os.getpid())
                    break
                metadata = exc.metadata() if isinstance(exc, AdapterParseError) else {}
                self.journal.fail(symbol, str(exc), **metadata)
                self.journal.heartbeat(phase="download", current_shard=None, pid=os.getpid())
            finally:
                progress = self.journal.data.get("retry_progress")
                status = self.journal.data["units"].get(symbol, {}).get("status")
                if progress and progress.get("active") and status in {"COMPLETE", "FAILED", "LEGAL_EMPTY", "NOT_COVERED"}:
                    progress["processed"] += 1
                    progress["recovered"] += int(status == "COMPLETE")
                    progress["failed"] += int(status == "FAILED")
                    self.journal._save()
        signal.signal(signal.SIGINT, previous_int)
        signal.signal(signal.SIGTERM, previous_term)
        return self.report()

    def restore_circuit_aborts(self) -> int:
        restored = 0
        for symbol, unit in self.journal.data["units"].items():
            if unit.get("status") == "FAILED" and str(unit.get("error", "")).startswith("eastmoney circuit open"):
                self.journal.pending(symbol, "deferred after upstream circuit-open")
                restored += 1
        return restored

    def repair_failed(self) -> dict:
        failed = {name: row for name, row in self.journal.data['units'].items() if row.get('status') == 'FAILED'}
        blocked = [name for name, row in failed.items() if row.get('category') == 'SYMBOL_DATA_ERROR' and row.get('adapter_version') == 'akshare-1.18.94' and 'NoneType' in str(row.get('error'))]
        selected = [name for name in failed if name not in blocked]
        if self.journal.data.get('retry_progress'):
            self.journal.data['retry_progress'].update(total=len(selected), skipped_same_adapter=len(blocked))
            self.journal._save()
        return {**self.run(selected, resume=False), 'skipped_same_adapter': len(blocked),
                'message': '相同适配器的确定性解析异常保留隔离；可指定少量分片诊断' if blocked else '重试结束'}

    def report(self) -> dict:
        states = [row.get("status") for row in self.journal.data["units"].values()]
        return {"total_shards": len(states), "completed": states.count("COMPLETE"), "failed": states.count("FAILED"), "legal_empty": states.count("LEGAL_EMPTY"), "not_covered": states.count("NOT_COVERED")}

    def archive_staged_results(self) -> int:
        """Content-address normalized landing files when an older run predates raw capture.

        This is explicitly a *result* artifact, never represented as the original
        upstream response.  It lets already-completed shards remain resumable
        without an unnecessary second upstream request.
        """
        if self.raw_store is None:
            return 0
        archived = 0
        for symbol, unit in self.journal.data["units"].items():
            if unit.get("status") != "COMPLETE" or unit.get("staged_result_sha256"):
                continue
            path = self.stage_root / "valuation_daily" / f"{symbol}.jsonl"
            if not path.is_file():
                raise RuntimeError(f"completed shard has no staging file: {symbol}")
            receipt = self.raw_store.put(f"valuation_daily/{symbol}/normalized-result", path.read_bytes())
            unit["staged_result_sha256"] = receipt["sha256"]
            unit["staged_result_bytes"] = receipt["bytes"]
            self.journal._save()
            archived += 1
        return archived

    def gap_report(self) -> dict:
        from .quality import validate_candidate
        units = self.journal.data["units"]
        checked = validate_candidate(self.stage_root, units, base_commit='UNBOUND', raw_store=self.raw_store)
        summaries = checked['shards'].values()
        failed = sorted(name for name, row in units.items() if row.get("status") == "FAILED")
        uncovered = sorted(name for name, row in units.items() if row.get("status") == "NOT_COVERED")
        legal_empty = sorted(name for name, row in units.items() if row.get("status") == "LEGAL_EMPTY")
        pending = sorted(name for name, row in units.items() if row.get("status") in {"PENDING", "RUNNING"})
        quality = "PARTIAL"
        return {**self.report(), "dataset": "valuation_daily", "row_count": checked['row_count'], "coverage_start": min((r['first_date'] for r in summaries if r['first_date']), default=None),
                "coverage_end": max((r['latest_date'] for r in summaries if r['latest_date']), default=None), "symbol_count": len(checked['accepted']), "missing_symbols": sorted(checked['isolated']),
                "failed_symbols": failed, "not_covered_symbols": uncovered, "legal_empty_symbols": legal_empty, "pending_symbols": pending,
                "error_classes": {name: units[name].get("error") for name in failed}, "duplicate_count": checked['duplicate_count'], "schema_error_count": checked['schema_error_count'],
                "quality_status": quality}
