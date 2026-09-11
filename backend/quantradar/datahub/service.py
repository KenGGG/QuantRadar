"""Small operational facade for the three DataHub V1 datasets."""

from __future__ import annotations

import hashlib
import json
import time
import fcntl
import os
import subprocess
import sys
from contextlib import contextmanager
from bisect import bisect_left
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import get_context
from pathlib import Path
from typing import Any, Callable, Iterable

import pymysql
from pymysql.cursors import DictCursor

from ..config import DataHubConfig, load_datahub_config
from .adapters import BaostockAdapter, FetchedRows, SwIndustryAdapter
from .dolt import SupplementalStore
from .pipeline import DataHubPipeline
from .release import ReleaseStore
from .store import RawStore, UpdateJournal, _atomic_json
from .governor import RequestGovernor, CircuitOpen
from .mvp import AkshareValuationFetcher, ShardRunner


def canonical_sh_sz_security_master(
    base_rows: Iterable[dict[str, Any]], lifecycle_rows: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Use the immutable base pool, adding only SH/SZ lifecycle records absent from it."""
    master: dict[str, dict[str, Any]] = {}
    for row in base_rows:
        symbol = str(row.get("symbol") or "")
        if len(symbol) == 9 and symbol[:6].isdigit() and symbol.endswith((".SH", ".SZ")):
            master[symbol] = dict(row)
    for row in lifecycle_rows:
        symbol = str(row.get("symbol") or "")
        if symbol not in master and len(symbol) == 9 and symbol[:6].isdigit() and symbol.endswith((".SH", ".SZ")):
            master[symbol] = dict(row)
    generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    records = []
    for symbol in sorted(master):
        row = dict(master[symbol])
        row["symbol"] = symbol
        row["exchange"] = symbol.rsplit(".", 1)[-1]
        row["first_seen_date"] = row.get("first_seen_date") or generated_at[:10]
        row["quality_status"] = row.get("quality_status") or row.get("pit_status") or "PARTIAL"
        row["provenance"] = {
            key: row.get(key) for key in ("source", "raw_sha256", "adapter_version", "fetched_at", "available_date", "pit_status")
        }
        records.append(row)
    return records


def _fetch_valuation_batch(host: str | None, symbols: list[str], start_date: str, end_date: str) -> list[tuple[str, FetchedRows]]:
    """Runs in its own process because the vendor SDK owns global socket state."""
    return list(BaostockAdapter(host=host).valuations(symbols, start_date, end_date))


def low_beta_status_coverage_outcome(missing_dates: list[str], base_price_last_date: str | None) -> str:
    """A missing state is legitimate only if fixed-base price ended first."""
    if missing_dates and base_price_last_date and str(base_price_last_date)[:10] < min(missing_dates):
        return "NOT_COVERED"
    return "UNRESOLVED"


def group_trade_status_candidates_by_day(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """Map requested external symbols by day for partition-pruned base reads."""
    from ..providers.investment_data.symbols import normalize_stock_symbol

    grouped: dict[str, dict[str, str]] = {}
    candidates = sorted({(str(row["trade_date"])[:10], str(row["symbol"])) for row in rows})
    for day, external in candidates:
        grouped.setdefault(day, {})[normalize_stock_symbol(external)] = external
    return grouped


class JsonlRows:
    """Repeatable disk staging for a full valuation backfill without RAM growth."""

    def __init__(self, path: Path, count: int = 0) -> None:
        self.path = path
        self.count = count if count else (sum(1 for line in path.open(encoding="utf-8") if line.strip()) if path.is_file() else 0)

    def append(self, rows: Iterable[dict[str, Any]]) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        added = 0
        with self.path.open("a", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                added += 1
        self.count += added
        return added

    def __iter__(self):
        if not self.path.is_file():
            return
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield json.loads(line)

    def __len__(self) -> int:
        return self.count


class ShardJsonlRows:
    """Repeatable per-symbol staging view used to publish without loading all rows."""

    def __init__(self, root: Path, units: dict[str, dict[str, Any]]) -> None:
        self.root = root
        self.units = {symbol: dict(unit) for symbol, unit in units.items() if unit.get("status") == "COMPLETE"}
        self.count = sum(int(unit.get("row_count") or 0) for unit in self.units.values())

    def __iter__(self):
        for symbol in sorted(self.units):
            path = self.root / f"{symbol}.jsonl"
            if not path.is_file():
                raise RuntimeError(f"completed shard has no staging file: {symbol}")
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        yield json.loads(line)

    def __len__(self) -> int:
        return self.count


class DataHubService:
    def __init__(self, config: DataHubConfig | None = None) -> None:
        self.config = config or load_datahub_config()
        self.releases = ReleaseStore(self.config.release_root)
        self.raw = RawStore(self.config.raw_root)

    def base_inventory(self, release_id: str | None = None) -> dict[str, Any]:
        """Scan the base material actually visible to one immutable release."""
        from .inventory import scan_base
        manifest = self.releases.resolve(release_id)
        base_commit = manifest["base_commit"]
        connection = pymysql.connect(
            host=self.config.base_host, port=self.config.base_port, user=self.config.user, password=self.config.password,
            database=f"{self.config.base_database}/{base_commit}", connect_timeout=self.config.connect_timeout,
            read_timeout=max(self.config.read_timeout, 300), charset="utf8mb4", cursorclass=DictCursor,
        )
        try:
            with connection.cursor() as cursor:
                inventory = scan_base(cursor)
        finally:
            connection.close()
        report = {"release_id": manifest["release_id"], "base_commit": base_commit,
                  "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **inventory}
        _atomic_json(Path(self.config.supplemental_repo) / "base_inventory.json", report)
        return report

    def strategy_gap_plan(self, start: str, end: str, release_id: str | None = None) -> dict[str, Any]:
        """Persist the actual strategy window before any source routing is considered."""
        from .inventory import build_gap_plan
        inventory = self.base_inventory(release_id)
        plan = build_gap_plan(inventory["domains"], start=start, end=end, requirements={
            "price": "base-final-price-v1", "trade_status": "base-bao-daily-v1",
        })
        from .work_queue import DataHubWorkQueue
        queue = DataHubWorkQueue(Path(self.config.supplemental_repo) / "work-queue.json")
        planned = []
        for gap in plan["strategy_gap"]:
            fingerprint = hashlib.sha256(json.dumps({"base_commit": inventory["base_commit"], **gap}, sort_keys=True).encode()).hexdigest()
            # The base contract identifies the missing material.  The work
            # order identifies the separately qualified source that may fill it.
            source_contract = "baostock-daily-v2" if gap["domain"] == "trade_status" else gap["source_contract_id"]
            planned.append(queue.enqueue("strategy", {
                "source_contract_id": source_contract, "base_source_contract_id": gap["source_contract_id"], "domain": gap["domain"], "fields": [], "symbols": [],
                "range": gap["range"], "gap_reason": "fixed-release strategy coverage gap", "gap_fingerprint": fingerprint,
                "boundary_check": {"before": gap["range"]["start"], "after": gap["range"]["end"]},
                "budget": {"network_attempts": "UNKNOWN_UNTIL_SOURCE_SELECTED"},
                "source_health": "QUALIFIED_SAMPLED" if source_contract == "baostock-daily-v2" else "UNASSESSED",
            }))
        report = {"release_id": inventory["release_id"], "base_commit": inventory["base_commit"],
                  "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **plan,
                  "work_orders": planned, "queue_status": queue.status()["counts"]}
        _atomic_json(Path(self.config.supplemental_repo) / "gap_plan.json", report)
        return report

    def _low_beta_status_dependencies(self, start: str, end: str, base_commit: str) -> list[dict[str, Any]]:
        """Read the fixed base calendar and CSI 300 snapshots for this strategy only."""
        from .inventory import monthly_status_dependencies
        connection = pymysql.connect(
            host=self.config.base_host, port=self.config.base_port, user=self.config.user, password=self.config.password,
            database=f"{self.config.base_database}/{base_commit}", connect_timeout=self.config.connect_timeout,
            read_timeout=max(self.config.read_timeout, 300), charset="utf8mb4", cursorclass=DictCursor,
        )
        try:
            with connection.cursor() as cursor:
                # One prior calendar date is required for the first monthly decision.
                cursor.execute(
                    "SELECT date FROM ts_trade_day_calendar WHERE exchange=%s AND is_open=1 "
                    "AND date <= %s ORDER BY date",
                    ("SSE", end),
                )
                days = [str(row["date"])[:10] for row in cursor.fetchall()]
                cache: dict[str, list[str]] = {}
                def constituents(day: str) -> list[str]:
                    if day not in cache:
                        cursor.execute(
                            "SELECT MAX(trade_date) AS trade_date FROM ts_index_weight "
                            "WHERE index_code=%s AND trade_date<=%s", ("000300.SH", day),
                        )
                        snapshot = cursor.fetchone()["trade_date"]
                        if snapshot is None:
                            cache[day] = []
                        else:
                            cursor.execute(
                                "SELECT stock_code FROM ts_index_weight WHERE index_code=%s AND trade_date=%s ORDER BY stock_code",
                                ("000300.SH", snapshot),
                            )
                            cache[day] = [str(row["stock_code"]) for row in cursor.fetchall()]
                    return cache[day]
                return monthly_status_dependencies(days, start=start, end=end, constituents_for=constituents)
        finally:
            connection.close()

    def low_beta_status_plan(self, start: str, end: str, release_id: str | None = None) -> dict[str, Any]:
        """Describe the strict saved low-Beta strategy's unfilled status work without fetching it."""
        manifest = self.releases.resolve(release_id)
        dependencies = self._low_beta_status_dependencies(start, end, manifest["base_commit"])
        tasks = []
        for dependency in dependencies:
            status_date = dependency["status_date"]
            fingerprint = hashlib.sha256(json.dumps({
                "release_id": manifest["release_id"], "base_commit": manifest["base_commit"],
                "status_date": status_date, "symbols": dependency["symbols"],
            }, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            tasks.append({
                "source_contract_id": "baostock-daily-v2", "base_source_contract_id": "base-bao-daily-v1",
                "domain": "trade_status", "fields": ["is_st", "tradestatus", "turn"],
                "symbols": dependency["symbols"], "range": {"start": status_date, "end": status_date},
                "rebalance_date": dependency["rebalance_date"], "gap_reason": "low-beta previous-trading-day status dependency",
                "gap_fingerprint": fingerprint, "boundary_check": dependency["boundary_check"],
                "budget": {"network_attempts": "ONE_BAOSTOCK_QUERY_PER_SYMBOL"}, "source_health": "QUALIFIED_SAMPLED",
            })
        plan_fingerprint = hashlib.sha256(json.dumps({
            "release_id": manifest["release_id"], "base_commit": manifest["base_commit"],
            "tasks": [{key: task[key] for key in ("range", "symbols", "gap_fingerprint")} for task in tasks],
        }, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        scope_fingerprint = hashlib.sha256(json.dumps({
            "base_commit": manifest["base_commit"],
            "tasks": [{key: task[key] for key in ("source_contract_id", "range", "symbols", "gap_fingerprint")} for task in tasks],
        }, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        return {"release_id": manifest["release_id"], "base_commit": manifest["base_commit"],
                "strategy": "low-beta-strict-monthly", "window": {"start": start, "end": end}, "tasks": tasks,
                "plan_fingerprint": plan_fingerprint, "scope_fingerprint": scope_fingerprint,
                "key_count": sum(len(task["symbols"]) for task in tasks),
                "symbol_count": len({symbol for task in tasks for symbol in task["symbols"]})}

    def _low_beta_status_journal(self, plan: dict[str, Any]) -> UpdateJournal:
        """Keep completed work reusable when only the release pointer changes."""
        root = Path(self.config.journal_root)
        scope = plan.get("scope_fingerprint")
        if not scope:
            return UpdateJournal(root / f"low-beta-status-{plan['plan_fingerprint'][:16]}.json")
        path = root / f"low-beta-status-scope-{scope[:16]}.json"
        if path.is_file():
            return UpdateJournal(path)
        expected = {symbol for task in plan["tasks"] for symbol in task["symbols"]}
        terminal = {"COMPLETE", "NOT_COVERED", "LEGAL_EMPTY"}
        legacy_paths = [root / f"low-beta-status-{plan['plan_fingerprint'][:16]}.json", *sorted(root.glob("low-beta-status-*.json"))]
        for legacy in legacy_paths:
            if not legacy.is_file() or legacy == path:
                continue
            try:
                data = json.loads(legacy.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            units = data.get("units", {})
            if set(units) != expected or not all(detail.get("status") in terminal for detail in units.values()):
                continue
            _atomic_json(path, {**data, "scope_fingerprint": scope, "migrated_from": legacy.name})
            break
        return UpdateJournal(path)

    def _base_price_last_dates(self, symbols: list[str], base_commit: str) -> dict[str, str | None]:
        from ..providers.investment_data.symbols import normalize_stock_symbol
        internal = [(symbol, normalize_stock_symbol(symbol)) for symbol in symbols]
        result = {symbol: None for symbol, _ in internal}
        connection = pymysql.connect(
            host=self.config.base_host, port=self.config.base_port, user=self.config.user, password=self.config.password,
            database=f"{self.config.base_database}/{base_commit}", connect_timeout=self.config.connect_timeout,
            read_timeout=max(self.config.read_timeout, 300), charset="utf8mb4", cursorclass=DictCursor,
        )
        try:
            with connection.cursor() as cursor:
                for offset in range(0, len(internal), 500):
                    chunk = internal[offset:offset + 500]
                    marks = ", ".join(["%s"] * len(chunk))
                    cursor.execute(
                        "SELECT symbol, MAX(tradedate) AS last_date FROM final_a_stock_eod_price "
                        f"WHERE symbol IN ({marks}) GROUP BY symbol", tuple(value for _, value in chunk),
                    )
                    external = {value: symbol for symbol, value in chunk}
                    for row in cursor.fetchall():
                        result[external[str(row["symbol"])]] = str(row["last_date"])[:10]
        finally:
            connection.close()
        return result

    def reconcile_low_beta_status_coverage(self, start: str, end: str, *, release_id: str | None = None) -> dict[str, Any]:
        """Turn source absences into NOT_COVERED only when the base price also ended."""
        plan = self.low_beta_status_plan(start, end, release_id)
        journal = self._low_beta_status_journal(plan)
        failed = {symbol: detail for symbol, detail in journal.data["units"].items() if detail.get("status") == "FAILED"}
        last_dates = self._base_price_last_dates(list(failed), plan["base_commit"])
        resolved, unresolved = [], []
        for symbol, detail in failed.items():
            missing = [part.strip() for part in str(detail.get("error", "")).partition(":")[2].split(",") if part.strip()]
            outcome = low_beta_status_coverage_outcome(missing, last_dates.get(symbol))
            if outcome == "NOT_COVERED":
                journal.data["units"][symbol] = {**detail, "status": "NOT_COVERED", "base_price_last_date": last_dates[symbol],
                                                  "coverage_evidence": "base final price ends before every missing requested status date"}
                resolved.append(symbol)
            else:
                unresolved.append(symbol)
        if resolved:
            journal._save()
        return {"not_covered": resolved, "unresolved": unresolved, "base_price_last_dates": last_dates}

    def collect_low_beta_status(self, start: str, end: str, *, release_id: str | None = None, limit: int = 0) -> dict[str, Any]:
        """Collect only strict low-Beta status dependencies into durable staging.

        This never publishes.  A completed symbol has one RawStore receipt and
        a JSONL projection containing only the exact date keys the strategy
        reads.  Failed symbols remain retryable in the journal.
        """
        plan = self.low_beta_status_plan(start, end, release_id)
        wanted = {
            (task["range"]["start"], symbol)
            for task in plan["tasks"] for symbol in task["symbols"]
        }
        symbols = sorted({symbol for _, symbol in wanted})
        journal = self._low_beta_status_journal(plan)
        journal.start("low-beta-status-repair", dataset="trade_status_daily")
        journal.ensure_pending(symbols, reason="strict low-beta monthly status dependency")
        selected = [symbol for symbol in symbols if journal.data["units"].get(symbol, {}).get("status") != "COMPLETE"]
        if limit:
            selected = selected[:limit]
        stage_root = Path(self.config.supplemental_repo) / "staging" / "low-beta-status"
        min_date, max_date = min(day for day, _ in wanted), max(day for day, _ in wanted)
        completed = failed = staged_rows = 0
        with self._updater_lock():
            journal.begin_job(total_shards=len(symbols), resume=True)
            journal.phase("download", "RUNNING")
            adapter = BaostockAdapter(host=self.config.baostock_host)
            try:
                for symbol, fetched in adapter.daily_bundles(selected, min_date, max_date):
                    journal.running(symbol)
                    journal.heartbeat(phase="download", current_shard=symbol, pid=os.getpid())
                    try:
                        receipt = self.raw.put(f"trade_status_daily/low-beta/{symbol}", fetched.raw_bytes)
                        if receipt["sha256"] != fetched.rows[0]["raw_sha256"]:
                            raise ValueError("raw receipt hash differs from normalized status candidate")
                        rows = [row for row in fetched.rows if (str(row["trade_date"])[:10], str(row["symbol"])) in wanted]
                        missing = sorted(day for day, expected_symbol in wanted if expected_symbol == symbol and not any(str(row["trade_date"])[:10] == day for row in rows))
                        if missing:
                            raise ValueError("missing requested status dates: " + ", ".join(missing))
                        content = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode()
                        path = stage_root / f"{symbol}.jsonl"
                        path.parent.mkdir(parents=True, exist_ok=True)
                        temporary = path.with_suffix(".tmp")
                        temporary.write_bytes(content)
                        os.replace(temporary, path)
                        journal.complete(symbol, raw_sha256=receipt["sha256"], row_count=len(rows), source="baostock",
                                         adapter_version=rows[0]["adapter_version"], first_date=min(row["trade_date"] for row in rows),
                                         last_date=max(row["trade_date"] for row in rows), staged_result_sha256=hashlib.sha256(content).hexdigest())
                        completed += 1
                        staged_rows += len(rows)
                    except Exception as exc:
                        journal.fail(symbol, str(exc), category="STATUS_DEPENDENCY_UNRESOLVED")
                        failed += 1
                    journal.heartbeat(phase="download", current_shard=None, pid=os.getpid())
            except Exception as exc:
                # The adapter session may fail between securities.  All
                # completed shards remain durable; the unvisited ones stay pending.
                journal.phase("download", "FAILED")
                return {"status": "PARTIAL", "error": str(exc), "completed": completed, "failed": failed,
                        "staged_rows": staged_rows, "remaining": len(selected) - completed - failed, "plan": plan}
            journal.phase("download", "DONE" if not failed else "FAILED")
        return {"status": "COMPLETE" if not failed and completed == len(selected) else "PARTIAL", "completed": completed,
                "failed": failed, "staged_rows": staged_rows, "remaining": len(symbols) - len(journal.completed_units()), "plan": plan}

    def publish_low_beta_status(self, start: str, end: str, *, release_id: str | None = None) -> dict[str, Any]:
        """Publish the staged low-Beta repair only when every planned symbol completed."""
        plan = self.low_beta_status_plan(start, end, release_id)
        journal = self._low_beta_status_journal(plan)
        units = journal.data["units"]
        incomplete = sorted(symbol for symbol, detail in units.items() if detail.get("status") not in {"COMPLETE", "NOT_COVERED"})
        if incomplete:
            raise RuntimeError(f"low-beta status repair has incomplete symbols: {len(incomplete)}")
        root = Path(self.config.supplemental_repo) / "staging" / "low-beta-status"
        rows = []
        for symbol in sorted(symbol for symbol, detail in units.items() if detail.get("status") == "COMPLETE"):
            path = root / f"{symbol}.jsonl"
            if not path.is_file():
                raise RuntimeError(f"completed status shard missing staging file: {symbol}")
            rows.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        if not rows:
            raise RuntimeError("no staged low-beta status rows")
        from .publication import publish_trade_status_patch
        result = publish_trade_status_patch(self, rows)
        journal.publish(result["release_id"])
        return result

    @contextmanager
    def _updater_lock(self):
        path = Path(self.config.supplemental_repo) / "datahub-updater.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("ALREADY_RUNNING") from exc
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def mvp_backfill(self, *, dataset: str, symbols: list[str], resume: bool, limit: int = 0) -> dict[str, Any]:
        """Run one serial, resumable MVP ingestion job without publishing."""
        if dataset != "valuation_daily":
            raise ValueError(f"MVP backfill is not yet implemented for {dataset}")
        operation_id = f"{dataset}-mvp"
        journal = UpdateJournal(Path(self.config.journal_root) / f"{operation_id}.json")
        governor = RequestGovernor(Path(self.config.supplemental_repo) / "governance", "eastmoney")
        fetcher = AkshareValuationFetcher(governor)
        runner = ShardRunner(Path(self.config.supplemental_repo) / "staging" / operation_id, journal, fetcher, self.raw)
        with self._updater_lock(), governor.operation_lock():
            runner.restore_circuit_aborts()
            journal.begin_job(total_shards=len(symbols[:limit] if limit else symbols), resume=resume)
            journal.ensure_pending(symbols[:limit] if limit else symbols, reason="canonical SH/SZ security master")
            journal.phase("download", "RUNNING")
            result = runner.run(symbols, resume=resume, limit=limit)
            journal.heartbeat(phase="download", current_shard=None, pid=os.getpid())
            journal.phase("download", "FAILED" if result["failed"] else "PAUSED" if runner.stop_requested or any(
                unit.get("status") == "PENDING" for unit in journal.data["units"].values()
            ) else "DONE")
        result["governor"] = governor.observed_status()
        result["journal"] = str(journal.path)
        return result

    def job_status(self) -> dict[str, Any]:
        journal = UpdateJournal(Path(self.config.journal_root) / "valuation_daily-mvp.json")
        units = list(journal.data.get("units", {}).values())
        states = {name: sum(item.get("status") == name for item in units) for name in
                  ("COMPLETE", "FAILED", "LEGAL_EMPTY", "NOT_COVERED", "PENDING", "RUNNING")}
        heartbeat, phase = journal.data.get("heartbeat") or {}, (journal.data.get("phases") or {}).get("download", {}).get("status")
        control = journal.data.get("control") or {}
        governor = RequestGovernor(Path(self.config.supplemental_repo) / "governance", "eastmoney").observed_status()
        from .daily import process_identity
        actual_identity = process_identity(heartbeat.get('pid'))
        worker_alive = bool(actual_identity and actual_identity == heartbeat.get('process_identity'))
        if actual_identity and not heartbeat.get('process_identity'):
            try:
                worker_alive = b'quantradar.datahub.cli' in Path(f"/proc/{heartbeat['pid']}/cmdline").read_bytes()
            except OSError:
                worker_alive = False
        if control.get("pause_requested"):
            status = "PAUSING" if worker_alive else "PAUSED"
        elif worker_alive:
            status = "RUNNING"
        elif governor.get("circuit_open"):
            status = "COOLDOWN"
        elif phase == "DONE": status = "COMPLETED"
        elif phase == "FAILED": status = "COMPLETED" if not states["PENDING"] and not states["RUNNING"] else "FAILED"
        elif phase == "PAUSED": status = "PAUSED"
        elif phase == "RUNNING": status = "PAUSED"
        else: status = "IDLE"
        # Older in-flight jobs predate the controller metadata.  Attach them to
        # the immutable base pool once so their UI percentage is never a false
        # 100% merely because only observed shards were counted.
        job = journal.data.get("job") or {}
        total = int(job.get("total_shards") or 0)
        if not total:
            total = len(self._base_lifecycle(persist_raw=False))
        processed = sum(states[name] for name in ("COMPLETE", "FAILED", "LEGAL_EMPTY", "NOT_COVERED"))
        states["PENDING"] = max(states["PENDING"], total - processed - states["RUNNING"])
        if status == "COMPLETED" and states["PENDING"]:
            status = "PAUSED"
        started = (journal.data.get("job") or {}).get("started_at") or journal.data.get("started_at")
        ended = time.time() if worker_alive else __import__('datetime').datetime.fromisoformat(heartbeat['last_heartbeat']).timestamp() if heartbeat.get('last_heartbeat') else time.time()
        elapsed = max(0.0, ended - __import__('datetime').datetime.fromisoformat(started).timestamp()) if started else 0.0
        rate = processed / elapsed if elapsed else 0.0
        return {"job_id": journal.data.get("operation_id"), "dataset": journal.data.get("dataset") or "valuation_daily",
                "status": status, "total_shards": total, "processed_shards": processed,
                "progress_percentage": round(100 * processed / total, 2) if total else 0,
                "counts": {key.lower(): value for key, value in states.items()}, "current_shard": heartbeat.get("current_shard"),
                "rows_downloaded": sum(int(item.get("row_count") or 0) for item in units),
                "coverage": self._stage_coverage(journal), "last_heartbeat": heartbeat.get("last_heartbeat"),
                "elapsed_seconds": round(elapsed, 1), "processing_rate": rate,
                "estimated_remaining_seconds": round((total - processed) / rate, 1) if rate else None,
                "governor": governor, "control": control,
                "worker_alive": worker_alive, "retry_progress": journal.data.get("retry_progress")}

    def _stage_coverage(self, journal: UpdateJournal) -> dict[str, Any]:
        dates = [(row.get("first_date"), row.get("last_date")) for row in journal.data.get("units", {}).values() if row.get("status") == "COMPLETE"]
        return {"coverage_start": min((a for a, _ in dates if a), default=None), "coverage_end": max((b for _, b in dates if b), default=None)}

    def start_job(self, *, dataset: str = "valuation_daily", limit: int = 0, resume: bool = True) -> dict[str, Any]:
        if self.job_status()["status"] in {"RUNNING", "PAUSING", "COOLDOWN"}:
            return {"status": "ALREADY_RUNNING", "job": self.job_status()}
        symbols = self.valuation_universe()
        command = [sys.executable, "-m", "quantradar.datahub.cli", "backfill", "--dataset", dataset]
        if resume: command.append("--resume")
        if limit: command.extend(["--limit", str(limit)])
        subprocess.Popen(command, cwd=str(Path(__file__).parents[3]), env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[3] / "backend")},
                         start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"status": "STARTED", "dataset": dataset, "limit": limit, "resume": resume, "total_shards": len(symbols[:limit] if limit else symbols)}

    def pause_job(self, *, stop: bool = False) -> dict[str, Any]:
        journal = UpdateJournal(Path(self.config.journal_root) / "valuation_daily-mvp.json")
        journal.request_pause(stop=stop)
        return self.job_status()

    def mvp_gaps(self, *, dataset: str = "valuation_daily") -> dict[str, Any]:
        if dataset != "valuation_daily":
            raise ValueError(f"MVP gaps are not yet implemented for {dataset}")
        journal = UpdateJournal(Path(self.config.journal_root) / "valuation_daily-mvp.json")
        runner = ShardRunner(Path(self.config.supplemental_repo) / "staging" / "valuation_daily-mvp", journal, lambda _: None, self.raw)
        runner.restore_circuit_aborts()
        runner.archive_staged_results()
        report = runner.gap_report()
        path = Path(self.config.supplemental_repo) / "staging" / "valuation_daily-mvp" / "gap_report.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        journal.record_audit(report)
        return {**report, "path": str(path)}

    def start_repair(self) -> dict[str, Any]:
        from .daily import DailyUpdate
        if DailyUpdate(self).status()['status'] == 'RUNNING':
            raise RuntimeError('统一更新正在运行，请稍后重试')
        job = self.job_status()
        if job["status"] in {"RUNNING", "PAUSING", "COOLDOWN"}:
            raise RuntimeError("采集任务正在运行或冷却，请稍后重试")
        if not job["counts"]["failed"]:
            return {"status": "NO_FAILED_SHARDS", "message": "没有需要重试的失败项"}
        units = UpdateJournal(Path(self.config.journal_root) / 'valuation_daily-mvp.json').data['units']
        failed = [u for u in units.values() if u.get('status') == 'FAILED']
        if failed and all(u.get('category') == 'SYMBOL_DATA_ERROR' and u.get('adapter_version') == 'akshare-1.18.94' and 'NoneType' in str(u.get('error')) for u in failed):
            return {'status': 'SOURCE_BLOCKED', 'message': f'{len(failed)} 项均为当前适配器解析异常；已停止同版本批量重复重试，需先核查来源响应。失败记录保留隔离。', 'failed': len(failed)}
        subprocess.Popen(
            [sys.executable, "-m", "quantradar.datahub.cli", "repair", "--dataset", "valuation_daily"],
            cwd=str(Path(__file__).parents[3]),
            env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[3] / "backend")},
            start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return {"status": "STARTED", "message": "已提交失败项重试，请查看采集进度", "failed": job["counts"]["failed"]}

    def mvp_repair(self, *, dataset: str, symbols: list[str] | None = None) -> dict[str, Any]:
        if dataset != "valuation_daily":
            raise ValueError(f"MVP repair is not yet implemented for {dataset}")
        journal = UpdateJournal(Path(self.config.journal_root) / "valuation_daily-mvp.json")
        if symbols and (len(symbols) > 3 or any(journal.data['units'].get(s, {}).get('status') != 'FAILED' for s in symbols)):
            raise ValueError('诊断修复仅接受最多三个现有 FAILED 分片')
        governor = RequestGovernor(Path(self.config.supplemental_repo) / "governance", "eastmoney")
        runner = ShardRunner(Path(self.config.supplemental_repo) / "staging" / "valuation_daily-mvp", journal, AkshareValuationFetcher(governor), self.raw)
        with self._updater_lock(), governor.operation_lock():
            journal.begin_job(total_shards=len(journal.data["units"]), resume=True)
            journal.data["retry_progress"] = {"total": sum(u.get("status") == "FAILED" for u in journal.data["units"].values()), "processed": 0, "recovered": 0, "failed": 0, "active": True}
            journal.phase("download", "RUNNING")
            journal.heartbeat(phase="download", current_shard=None, pid=os.getpid())
            result = runner.run(symbols, resume=False) if symbols else runner.repair_failed()
            journal.data["retry_progress"]["active"] = False
            journal.heartbeat(phase="download", current_shard=None, pid=0)
            journal.phase("download", "PAUSED" if runner.stop_requested else "FAILED" if result["failed"] else "DONE")
            journal.record_repair(result)
        return {**result, "governor": governor.observed_status()}

    def resolve_false_positive_circuit(self, *, symbol: str, dataset: str = "valuation_daily") -> dict[str, Any]:
        """Record a local parse failure, then clear only its wrongly-opened circuit."""
        if dataset != "valuation_daily":
            raise ValueError(f"MVP circuit resolution is not implemented for {dataset}")
        journal = UpdateJournal(Path(self.config.journal_root) / "valuation_daily-mvp.json")
        governor = RequestGovernor(Path(self.config.supplemental_repo) / "governance", "eastmoney")
        evidence = governor.status().get("last_error") or {}
        journal.fail(symbol, str(evidence.get("message") or "AKShare public API parse failure"),
                     category="SYMBOL_DATA_ERROR", exception_type="AdapterParseError",
                     adapter="akshare.stock_value_em", adapter_version="akshare-1.18.94",
                     request_metadata=evidence, raw_status="UNAVAILABLE_SDK_EXCEPTION")
        resolution = governor.resolve_false_positive(symbol=symbol.split(".")[0], reason="FALSE_POSITIVE_SYMBOL_PARSE_ERROR")
        return {"symbol": symbol, "shard_status": "FAILED", "circuit_open": resolution["circuit_open"],
                "circuit_audit": resolution["circuit_audit"][-1]}

    def mvp_health_probe(self, *, symbols: list[str]) -> dict[str, Any]:
        """Serial three-symbol check before resuming a paused valuation backfill."""
        if len(symbols) != 3 or len(set(symbols)) != 3:
            raise ValueError("health probe requires exactly three distinct symbols")
        journal = UpdateJournal(Path(self.config.journal_root) / "valuation_daily-mvp.json")
        governor = RequestGovernor(Path(self.config.supplemental_repo) / "governance", "eastmoney")
        runner = ShardRunner(Path(self.config.supplemental_repo) / "staging" / "valuation_daily-mvp", journal,
                             AkshareValuationFetcher(governor), self.raw)
        with self._updater_lock(), governor.operation_lock():
            journal.phase("download", "RUNNING")
            # Health probes deliberately target terminal failures.  A normal
            # resume skips them, which would turn every probe into a false
            # negative without ever calling the source.
            result = runner.run(symbols, resume=False)
            selected = {symbol: (journal.data.get("units", {}).get(symbol) or {}).get("status", "PENDING") for symbol in symbols}
            healthy = all(status == "COMPLETE" for status in selected.values()) and not governor.status().get("circuit_open")
            journal.heartbeat(phase="download", current_shard=None, pid=os.getpid())
            journal.phase("download", "PAUSED")
            journal.record_probe(symbols=symbols, outcome="HEALTHY" if healthy else "UNHEALTHY",
                                 details={"result": result, "selected": selected, "governor": governor.status()})
        return {"outcome": "HEALTHY" if healthy else "UNHEALTHY", "result": result, "selected": selected, "governor": governor.status()}

    def _staged_valuations(self) -> ShardJsonlRows:
        journal = UpdateJournal(Path(self.config.journal_root) / "valuation_daily-mvp.json")
        root = Path(self.config.supplemental_repo) / "staging" / "valuation_daily-mvp" / "valuation_daily"
        rows = ShardJsonlRows(root, journal.data["units"])
        if not len(rows):
            raise RuntimeError("no completed valuation staging rows")
        return rows

    def _existing_industries(self) -> list[dict[str, Any]]:
        """Carry forward the already-qualified SW staging, never the frozen valuation source."""
        manifest = self.releases.current()
        connection = self._connection(f"{self.config.supplemental_database}/{manifest['supplemental_commit']}")
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT symbol, industry_code, effective_from, effective_to, source, raw_sha256, adapter_version, fetched_at, available_date, pit_status FROM qr_sw_industry_history")
                rows = list(cursor.fetchall())
            if not rows:
                raise RuntimeError("qualified SW history is empty")
            return rows
        finally:
            connection.close()

    def _base_lifecycle(self, *, persist_raw: bool = True, base_commit: str | None = None) -> list[dict[str, Any]]:
        """Use the approved read-only base listing table with explicit BASE_EXISTING provenance."""
        base_commit = base_commit or self._base_commit()
        connection = pymysql.connect(
            host=self.config.base_host, port=self.config.base_port, user=self.config.user, password=self.config.password,
            database=f"{self.config.base_database}/{base_commit}", connect_timeout=self.config.connect_timeout,
            read_timeout=self.config.read_timeout, charset="utf8mb4", cursorclass=DictCursor,
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT ts_code, list_date, delist_date FROM ts_a_stock_list WHERE list_date IS NOT NULL")
                base_rows = list(cursor.fetchall())
        finally:
            connection.close()
        fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        raw = json.dumps(base_rows, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode()
        receipt = self.raw.put("security_lifecycle/investment_data-ts_a_stock_list", raw) if persist_raw else {"sha256": hashlib.sha256(raw).hexdigest()}
        rows = []
        for item in base_rows:
            symbol = str(item["ts_code"])
            if len(symbol) != 9 or not symbol[:6].isdigit() or not symbol.endswith((".SH", ".SZ")):
                continue
            listed, delisted = str(item["list_date"]), item.get("delist_date")
            rows.append({"symbol": symbol, "list_date": listed[:10], "delist_date": str(delisted)[:10] if delisted else None,
                         "status": "DELISTED" if delisted else "LISTED", "source": "investment_data:ts_a_stock_list:BASE_EXISTING",
                         "raw_sha256": receipt["sha256"], "adapter_version": "investment_data@" + base_commit,
                         "fetched_at": fetched_at, "available_date": None, "pit_status": "PARTIAL"})
        if not rows:
            raise RuntimeError("base lifecycle query produced no Shanghai/Shenzhen securities")
        return rows

    def base_trade_status_keys(self, rows: Iterable[dict[str, Any]], *, base_commit: str) -> set[tuple[str, str]]:
        """Return candidate keys already observed in the immutable base table.

        This is intentionally a narrow, commit-qualified read used by status
        publication.  A supplemental record may fill an absent date, but must
        never compete with a status observation already present in the base.
        """
        grouped = group_trade_status_candidates_by_day(rows)
        if not grouped:
            return set()
        connection = pymysql.connect(
            host=self.config.base_host, port=self.config.base_port, user=self.config.user, password=self.config.password,
            database=f"{self.config.base_database}/{base_commit}", connect_timeout=self.config.connect_timeout,
            read_timeout=self.config.read_timeout, charset="utf8mb4", cursorclass=DictCursor,
        )
        found: set[tuple[str, str]] = set()
        try:
            with connection.cursor() as cursor:
                # Equality on tradedate lets Dolt prune to one daily partition.
                # The old row-constructor IN scan touched every partition.
                for day, external_by_internal in grouped.items():
                    internal_symbols = sorted(external_by_internal)
                    for offset in range(0, len(internal_symbols), 500):
                        chunk = internal_symbols[offset:offset + 500]
                        marks = ", ".join(["%s"] * len(chunk))
                        cursor.execute(
                            "SELECT tradedate, symbol FROM bao_a_stock_eod_info "
                            f"WHERE tradedate=%s AND symbol IN ({marks})",
                            (day, *chunk),
                        )
                        for item in cursor.fetchall():
                            internal_symbol = str(item["symbol"])
                            external = external_by_internal.get(internal_symbol)
                            if external:
                                found.add((day, external))
        finally:
            connection.close()
        return found

    def supplemental_trade_status_rows(self, rows: Iterable[dict[str, Any]], *, supplemental_commit: str | None) -> dict[tuple[str, str], dict]:
        """Read matching records from a fixed supplemental commit for retry safety."""
        if not supplemental_commit:
            return {}
        candidates = sorted({(str(row["trade_date"])[:10], str(row["symbol"])) for row in rows})
        if not candidates:
            return {}
        connection = self._connection(f"{self.config.supplemental_database}/{supplemental_commit}")
        result: dict[tuple[str, str], dict] = {}
        try:
            with connection.cursor() as cursor:
                for offset in range(0, len(candidates), 500):
                    chunk = candidates[offset:offset + 500]
                    marks = ", ".join(["(%s, %s)"] * len(chunk))
                    cursor.execute(
                        "SELECT trade_date, symbol, tradestatus, is_st, turn, source, raw_sha256, adapter_version, available_date, pit_status "
                        "FROM qr_trade_status_daily WHERE (trade_date, symbol) IN (" + marks + ")",
                        tuple(value for item in chunk for value in item),
                    )
                    for item in cursor.fetchall():
                        result[(str(item["trade_date"])[:10], str(item["symbol"]))] = item
        finally:
            connection.close()
        return result

    def _security_master_path(self) -> Path:
        return Path(self.config.supplemental_repo) / "security-master" / "sh_sz.json"

    def _supplemental_lifecycle_candidates(self) -> list[dict[str, Any]]:
        connection = self._connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT symbol, list_date, delist_date, status, source, raw_sha256, adapter_version, fetched_at, available_date, pit_status FROM qr_security_lifecycle")
                return list(cursor.fetchall())
        finally:
            connection.close()

    def refresh_security_master(self) -> dict[str, Any]:
        """Build a governed ingestion pool; it is metadata, not a fourth formal dataset."""
        base = self._base_lifecycle(persist_raw=False)
        candidates = self._supplemental_lifecycle_candidates()
        rows = canonical_sh_sz_security_master(base, candidates)
        base_symbols = {row["symbol"] for row in base}
        delta = [row for row in rows if row["symbol"] not in base_symbols]
        version = hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
        payload = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "base_commit": self._base_commit(), "scope": "SH/SZ A shares; supplemental lifecycle candidates remain PARTIAL",
                   "version": version, "base_symbol_count": len(base), "delta_symbol_count": len(delta), "symbol_count": len(rows), "records": rows}
        path = self._security_master_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")
        os.replace(temporary, path)
        journal = UpdateJournal(Path(self.config.journal_root) / "valuation_daily-mvp.json")
        pending_created = journal.ensure_pending([row["symbol"] for row in delta], reason="canonical SH/SZ security-master delta")
        journal.set_total_shards(len(rows))
        return {key: payload[key] for key in ("base_commit", "version", "base_symbol_count", "delta_symbol_count", "symbol_count", "scope")} | {"path": str(path), "pending_created": pending_created}

    def valuation_universe(self) -> list[str]:
        """Canonical SH/SZ ingestion pool, never described as an all-market universe."""
        path = self._security_master_path()
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            return [str(row["symbol"]) for row in data.get("records", [])]
        return sorted(row["symbol"] for row in self._base_lifecycle(persist_raw=False))

    def mvp_publish(self) -> dict[str, Any]:
        """Legacy entry delegates to the same candidate checks as daily updates."""
        from .daily import DailyUpdate
        return DailyUpdate(self).start('publish')

    def _connection(self, database: str | None = None):
        return pymysql.connect(
            host=self.config.supplemental_host, port=self.config.supplemental_port,
            user=self.config.user, password=self.config.password,
            database=database or self.config.supplemental_database, connect_timeout=self.config.connect_timeout,
            read_timeout=self.config.read_timeout, charset="utf8mb4", cursorclass=DictCursor,
        )

    def _base_commit(self) -> str:
        connection = pymysql.connect(
            host=self.config.base_host, port=self.config.base_port, user=self.config.user,
            password=self.config.password, database=self.config.base_database,
            connect_timeout=self.config.connect_timeout, read_timeout=self.config.read_timeout,
            charset="utf8mb4", cursorclass=DictCursor,
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT DOLT_HASHOF('HEAD') AS commit_hash")
                row = cursor.fetchone()
            if not row or not row.get("commit_hash"):
                raise RuntimeError("investment_data did not return a Dolt commit")
            return str(row["commit_hash"])
        finally:
            connection.close()

    @staticmethod
    def _retry(operation: Callable[[], FetchedRows], attempts: int) -> FetchedRows:
        error: Exception | None = None
        for attempt in range(max(1, attempts)):
            try:
                return operation()
            except Exception as exc:  # source boundaries need a bounded retry
                error = exc
                if attempt + 1 < attempts:
                    time.sleep(2 ** attempt)
        raise RuntimeError(str(error)) from error

    def status(self) -> dict[str, Any]:
        operational = self._mvp_operational_status()
        try:
            manifest = self.releases.current()
        except FileNotFoundError:
            return {"current_release": None, "datasets": [], "last_success": None, "last_failure": self._last_failure(), "operational": operational}
        result = {
            "current_release": manifest,
            "datasets": [dict(name=name, **detail) for name, detail in manifest.get("datasets", {}).items()],
            "last_success": manifest.get("published_at"),
            "last_failure": self._last_failure(),
            "operational": operational,
        }
        try:
            audit = self.audit(manifest["release_id"])
            metrics = audit["datasets"]
            for dataset in result["datasets"]:
                table = {"valuation_daily": "qr_valuation_daily", "sw_industry_history": "qr_sw_industry_history", "security_lifecycle": "qr_security_lifecycle"}[dataset["name"]]
                dataset.update(metrics.get(table) or {})
        except Exception as exc:
            result["audit_error"] = str(exc)
        return result

    def _mvp_operational_status(self) -> dict[str, Any]:
        journal = UpdateJournal(Path(self.config.journal_root) / "valuation_daily-mvp.json")
        units = journal.data.get("units", {})
        states = [item.get("status") for item in units.values()]
        governor = RequestGovernor(Path(self.config.supplemental_repo) / "governance", "eastmoney").observed_status()
        return {"dataset": "valuation_daily", "completed": states.count("COMPLETE"), "failed": states.count("FAILED"),
                "legal_empty": states.count("LEGAL_EMPTY"), "not_covered": states.count("NOT_COVERED"),
                "pending": states.count("PENDING") + states.count("RUNNING"), "heartbeat": journal.data.get("heartbeat"),
                "phases": journal.data.get("phases", {}), "request_ledger": governor}

    def _last_failure(self) -> dict[str, Any] | None:
        root = Path(self.config.journal_root)
        failures = []
        for path in root.glob("*.json") if root.is_dir() else ():
            data = json.loads(path.read_text(encoding="utf-8"))
            failed = data.get("units", {})
            messages = {name: row.get("error") for name, row in failed.items() if row.get("status") == "FAILED"}
            if messages:
                failures.append({"operation_id": data.get("operation_id"), "failures": messages, "started_at": data.get("started_at")})
        return max(failures, key=lambda row: row.get("started_at") or "") if failures else None

    def audit(self, release_id: str | None = None) -> dict[str, Any]:
        manifest = self.releases.resolve(release_id)
        connection = self._connection(f"{self.config.supplemental_database}/{manifest['supplemental_commit']}")
        try:
            with connection.cursor() as cursor:
                output = {}
                for table, date_col in (("qr_valuation_daily", "trade_date"), ("qr_sw_industry_history", "effective_from"), ("qr_security_lifecycle", "list_date")):
                    cursor.execute(f"SELECT COUNT(*) AS row_count, MIN({date_col}) AS first_date, MAX({date_col}) AS latest_date, COUNT(DISTINCT symbol) AS stocks, SUM(pit_status <> 'PASS') AS partial_rows FROM {table}")
                    output[table] = cursor.fetchone()
                cursor.execute("SHOW COLUMNS FROM qr_valuation_daily")
                valuation_columns = {str(row["Field"]) for row in cursor.fetchall()}
                pcf_column = "pcf_ocf_ttm" if "pcf_ocf_ttm" in valuation_columns else "pcf_ncf_ttm" if "pcf_ncf_ttm" in valuation_columns else None
                if not pcf_column:
                    raise RuntimeError("valuation release has neither pcf_ocf_ttm nor legacy pcf_ncf_ttm")
                cursor.execute(
                    "SELECT SUM(pe_ttm IS NULL) AS pe_ttm, SUM(pb_mrq IS NULL) AS pb_mrq, "
                    f"SUM(ps_ttm IS NULL) AS ps_ttm, SUM({pcf_column} IS NULL) AS {pcf_column} FROM qr_valuation_daily"
                )
                output["qr_valuation_daily"]["source_nulls"] = cursor.fetchone()
                if pcf_column == "pcf_ncf_ttm":
                    output["qr_valuation_daily"]["source_nulls"]["pcf_ocf_ttm"] = None
                    output["qr_valuation_daily"]["pcf_semantics"] = "LEGACY_PCF_NCF_TTM: not equivalent to current Pcf OCF TTM"
                cursor.execute(
                    "SELECT COUNT(*) AS conflicts FROM qr_sw_industry_history AS earlier "
                    "JOIN qr_sw_industry_history AS later ON earlier.symbol = later.symbol "
                    "AND earlier.effective_from < later.effective_from "
                    "AND (earlier.effective_to IS NULL OR earlier.effective_to >= later.effective_from)"
                )
                output["qr_sw_industry_history"]["conflicts"] = cursor.fetchone()["conflicts"]
                cursor.execute("SELECT SUM(status = 'DELISTED') AS delisted_stocks FROM qr_security_lifecycle")
                output["qr_security_lifecycle"]["delisted_stocks"] = cursor.fetchone()["delisted_stocks"]
                cursor.execute(
                    "SELECT symbol, COUNT(*) AS observed_rows, SUM(pe_ttm IS NOT NULL) AS pe_ttm, "
                    "SUM(pb_mrq IS NOT NULL) AS pb_mrq, SUM(ps_ttm IS NOT NULL) AS ps_ttm, "
                    f"SUM({pcf_column} IS NOT NULL) AS {pcf_column} FROM qr_valuation_daily GROUP BY symbol"
                )
                valuation_rows = {row["symbol"]: row for row in cursor.fetchall()}
                if pcf_column == "pcf_ncf_ttm":
                    for row in valuation_rows.values():
                        row["pcf_ocf_ttm"] = 0
                cursor.execute("SELECT symbol, list_date, delist_date FROM qr_security_lifecycle")
                lifecycle_rows = list(cursor.fetchall())
                output["qr_valuation_daily"]["coverage"] = self._valuation_coverage(
                    manifest, lifecycle_rows, valuation_rows
                )
            return {"release_id": manifest["release_id"], "datasets": output, "pit_status": {name: row.get("pit_status") for name, row in manifest.get("datasets", {}).items()}}
        finally:
            connection.close()

    def _valuation_coverage(
        self, manifest: dict[str, Any], lifecycle_rows: list[dict[str, Any]], valuation_rows: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        """Classify V1 coverage against the explicit lifecycle pool and base trading calendar."""
        valuation = manifest.get("datasets", {}).get("valuation_daily", {})
        start = "2016-01-01"
        end = str(valuation.get("latest_date") or "")
        if not end:
            return {"status": "UNVERIFIED", "reason": "valuation dataset has no latest date"}
        base = pymysql.connect(
            host=self.config.base_host, port=self.config.base_port, user=self.config.user,
            password=self.config.password, database=f"{self.config.base_database}/{manifest['base_commit']}",
            connect_timeout=self.config.connect_timeout, read_timeout=self.config.read_timeout,
            charset="utf8mb4", cursorclass=DictCursor,
        )
        try:
            with base.cursor() as cursor:
                cursor.execute(
                    "SELECT date FROM ts_trade_day_calendar WHERE exchange = 'SSE' AND is_open = 1 "
                    "AND date >= %s AND date <= %s ORDER BY date", (start, end)
                )
                trading_days = [str(row["date"]) for row in cursor.fetchall()]
        finally:
            base.close()
        expected = not_yet_listed = source_not_covered = 0
        fields = {name: 0 for name in ("pe_ttm", "pb_mrq", "ps_ttm", "pcf_ocf_ttm")}
        for row in lifecycle_rows:
            listed = str(row["list_date"])
            delisted = str(row["delist_date"]) if row.get("delist_date") else end
            not_yet_listed += max(0, bisect_left(trading_days, min(listed, end)) - bisect_left(trading_days, start))
            active_start = max(start, listed)
            active_end = min(end, delisted)
            active = max(0, bisect_left(trading_days, active_end) - bisect_left(trading_days, active_start))
            expected += active
            observed = valuation_rows.get(row["symbol"], {})
            source_not_covered += max(0, active - int(observed.get("observed_rows") or 0))
            for field in fields:
                fields[field] += int(observed.get(field) or 0)
        return {
            "status": "PARTIAL",
            "pool": "qr_security_lifecycle",
            "start": start,
            "end": end,
            "trading_days": len(trading_days),
            "eligible_stock_days": expected,
            "not_yet_listed_stock_days": not_yet_listed,
            "source_not_covered_stock_days": source_not_covered,
            "field_present_stock_days": fields,
            "acquisition_failed_stock_days": 0,
            "note": "Source-reported empty values are separately reported as source_nulls; this source cannot establish historical publication availability.",
        }

    def update(self, *, mode: str, start_date: str, end_date: str, symbols: list[str] | None = None, attempts: int = 3) -> dict[str, Any]:
        """Extract all sources to durable staging, then atomically publish one paired release."""
        if mode not in {"backfill", "sync"}:
            raise ValueError("mode must be backfill or sync")
        operation_key = hashlib.sha256(json.dumps([mode, start_date, end_date, sorted(symbols or [])]).encode()).hexdigest()[:16]
        journal = UpdateJournal(Path(self.config.journal_root) / f"{mode}-{operation_key}.json")
        journal.start(f"{mode}-{operation_key}", dataset="valuation_daily")
        previous_release = journal.published_release()
        if previous_release:
            return self.releases.resolve(previous_release)
        baostock, sw = BaostockAdapter(host=self.config.baostock_host), SwIndustryAdapter(ca_bundle=self.config.sw_ca_bundle)
        try:
            lifecycle = self._retry(baostock.lifecycle, attempts)
        except Exception as exc:
            journal.fail("security_lifecycle:extract", str(exc))
            raise
        selected = symbols or [row["symbol"] for row in lifecycle.rows]
        stage = JsonlRows(Path(self.config.supplemental_repo) / "staging" / f"{mode}-{operation_key}-valuation.jsonl")
        for attempt in range(max(1, attempts)):
            completed = journal.completed_units()
            pending = [symbol for symbol in selected if f"{symbol}:{start_date}:{end_date}" not in completed]
            if not pending:
                break
            batches = [pending[index:index + 24] for index in range(0, len(pending), 24)]
            failed_batches: list[list[str]] = []
            try:
                # Fork inherits BaoStock's module-global socket context.  Spawn starts
                # clean interpreter sessions, which is the only safe form of parallelism
                # for this SDK.
                with ProcessPoolExecutor(
                    max_workers=min(self.config.fetch_workers, len(batches)), mp_context=get_context("spawn")
                ) as pool:
                    futures = {
                        pool.submit(_fetch_valuation_batch, self.config.baostock_host, batch, start_date, end_date): batch
                        for batch in batches
                    }
                    for future in as_completed(futures):
                        batch = futures[future]
                        try:
                            fetched_rows = future.result()
                        except Exception:
                            failed_batches.append(batch)
                            continue
                        for symbol, fetched in fetched_rows:
                            unit = f"{symbol}:{start_date}:{end_date}"
                            receipt = self.raw.put(f"valuation_daily/{unit}", fetched.raw_bytes)
                            if fetched.rows and any(row["raw_sha256"] != receipt["sha256"] for row in fetched.rows):
                                raise RuntimeError("normalized valuation raw hash does not match persisted bytes")
                            stage.append(fetched.rows)
                            journal.complete(unit, raw_sha256=str(receipt["sha256"]), row_count=len(fetched.rows))
                if not failed_batches:
                    break
                raise RuntimeError(f"Baostock valuation extraction failed for {sum(map(len, failed_batches))} symbols")
            except Exception as exc:
                if attempt + 1 >= max(1, attempts):
                    journal.fail("valuation_daily:extract", str(exc))
                    raise
                time.sleep(2 ** attempt)
        try:
            industry = self._retry(sw.history, attempts)
        except Exception as exc:
            journal.fail("sw_industry_history:extract", str(exc))
            raise
        writer_connection = self._connection()
        try:
            writer = SupplementalStore(writer_connection)
            pipeline = DataHubPipeline(self.config.supplemental_repo, releases=self.releases, writer=writer, base_commit=self._base_commit, raw_store=self.raw)
            manifest = pipeline.publish({"valuation_daily": lambda: stage, "sw_industry_history": lambda: industry, "security_lifecycle": lambda: lifecycle})
            journal.publish(manifest["release_id"])
            return manifest
        finally:
            writer_connection.close()
