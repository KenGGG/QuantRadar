"""Fail-closed DataHub publication pipeline.

Fetch callbacks produce already-normalized staged rows.  All callbacks finish
before the supplemental Dolt working set is touched; publication occurs only
after a successful supplemental commit and an atomic manifest switch.
"""

from __future__ import annotations

import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterable

from .release import ReleaseStore


class UpdateFailure(RuntimeError):
    pass


class DataHubPipeline:
    def __init__(
        self,
        runtime_root: Path | str,
        *,
        releases: ReleaseStore,
        writer: Any,
        base_commit: Callable[[], str],
        raw_store: Any | None = None,
    ) -> None:
        self.runtime_root = Path(runtime_root)
        self.releases = releases
        self.writer = writer
        self.base_commit = base_commit
        self.raw_store = raw_store

    @contextmanager
    def _lock(self):
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        with (self.runtime_root / "update.lock").open("a+") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise UpdateFailure("another DataHub update is already running") from exc
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def publish(self, datasets: dict[str, Callable[[], Iterable[dict[str, Any]]]], *, extra_metadata: dict[str, dict[str, Any]] | None = None,
                release_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        expected = ("valuation_daily", "sw_industry_history", "security_lifecycle")
        missing = [name for name in expected if name not in datasets]
        if missing:
            raise UpdateFailure(f"required datasets missing from update: {', '.join(missing)}")
        with self._lock():
            staged: dict[str, Iterable[dict[str, Any]]] = {}
            for name in expected:
                try:
                    fetched = datasets[name]()
                except Exception as exc:  # preserve source and dataset in persistent operator error
                    raise UpdateFailure(f"{name} extract/stage failed: {exc}") from exc
                if hasattr(fetched, "raw_bytes") and hasattr(fetched, "rows"):
                    if self.raw_store is None:
                        raise UpdateFailure(f"{name} supplied source bytes but no RawStore is configured")
                    receipt = self.raw_store.put(f"{name}/{getattr(fetched, 'fetched_at', 'unknown')}", fetched.raw_bytes)
                    rows = fetched.rows
                    expected_hashes = {row.get("raw_sha256") for row in rows if row.get("raw_sha256")}
                    if expected_hashes and expected_hashes != {receipt["sha256"]}:
                        raise UpdateFailure(f"{name} normalized rows do not match persisted raw bytes")
                else:
                    rows = fetched
                if not hasattr(rows, "__iter__") or not hasattr(rows, "__len__"):
                    raise UpdateFailure(f"{name} produced non-repeatable staging rows")
                staged[name] = rows

            for name, rows in staged.items():
                if len(rows) == 0:
                    raise UpdateFailure(f"quality gate failed: {name} has no rows")

            # All extracts are staged successfully: only now can supplemental working state change.
            try:
                self.writer.ensure_schema()
                prepare = getattr(self.writer, "prepare_canonical_valuation", None)
                if prepare is not None:
                    prepare()
                self.writer.upsert_valuations(staged["valuation_daily"])
                self.writer.upsert_industries(staged["sw_industry_history"])
                self.writer.upsert_lifecycles(staged["security_lifecycle"])
                supplemental_commit = self.writer.commit("datahub: publish staged V1 datasets")
                revision_counts = getattr(self.writer, "revision_counts", lambda _commit: {})(supplemental_commit)
                base_commit = self.base_commit()
                if not base_commit:
                    raise ValueError("base Dolt did not return a commit hash")
            except Exception as exc:
                raise UpdateFailure(f"supplemental audit/commit failed: {exc}") from exc

            metadata = {name: self._metadata(name, rows) for name, rows in staged.items()}
            for name, values in (extra_metadata or {}).items():
                if name in metadata:
                    metadata[name].update(values)
            for name, count in revision_counts.items():
                if name in metadata:
                    metadata[name]["history_revision_count"] = int(count)
            return self.releases.publish(
                base_commit=base_commit,
                supplemental_commit=supplemental_commit,
                datasets=metadata,
                source_adapters={"a-stock-data": "2012ce7cd0e75d379c5e6cbd3115514f300f3bc8"},
                metadata=release_metadata,
            )

    @staticmethod
    def _pit_status(rows: Iterable[dict[str, Any]]) -> str:
        statuses = {str(row.get("pit_status", "UNVERIFIED")) for row in rows}
        if not statuses:
            return "PARTIAL"
        if "UNVERIFIED" in statuses:
            return "UNVERIFIED"
        if "PARTIAL" in statuses:
            return "PARTIAL"
        return "PASS"

    @staticmethod
    def _row_count(rows: Iterable[dict[str, Any]]) -> int:
        if hasattr(rows, "__len__"):
            return len(rows)  # type: ignore[arg-type]
        return sum(1 for _ in rows)

    @classmethod
    def _metadata(cls, name: str, rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
        date_field = {"valuation_daily": "trade_date", "sw_industry_history": "effective_from", "security_lifecycle": "list_date"}[name]
        first_date = latest_date = None
        stocks: set[str] = set()
        sources: set[str] = set()
        for row in rows:
            value = row.get(date_field)
            if value is not None:
                value = str(value)
                first_date = value if first_date is None or value < first_date else first_date
                latest_date = value if latest_date is None or value > latest_date else latest_date
            if row.get("symbol"):
                stocks.add(str(row["symbol"]))
            if row.get("source"):
                sources.add(str(row["source"]))
        return {
            "version": "v1", "pit_status": cls._pit_status(rows), "row_count": cls._row_count(rows),
            "first_date": first_date, "latest_date": latest_date, "stocks": len(stocks), "source": sorted(sources),
        }
