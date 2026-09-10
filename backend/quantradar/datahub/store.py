"""Durable raw source artifacts and resumable update journals."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


class RawStore:
    """Content-addressed source bytes; logical source names are audit metadata only."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.raw_dir = self.root / "raw"

    def put(self, logical_name: str, content: bytes) -> dict[str, str | int]:
        sha256 = hashlib.sha256(content).hexdigest()
        path = self.raw_dir / sha256
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if self.read(sha256) != content:
                raise ValueError(f"existing raw artifact hash mismatch: {sha256}")
        else:
            temporary = path.with_name(f".{sha256}.{os.getpid()}.tmp")
            with temporary.open("wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        return {"logical_name": logical_name, "sha256": sha256, "bytes": len(content)}

    def read(self, sha256: str) -> bytes:
        path = self.raw_dir / sha256
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != sha256:
            raise ValueError(f"raw artifact hash mismatch: {sha256}")
        return content


class UpdateJournal:
    """One small durable record per operation; failed chunks are intentionally retryable."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        if self.path.is_file():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return {"operation_id": None, "dataset": None, "units": {}, "phases": {}, "heartbeat": None,
                "control": {"pause_requested": False, "stop_requested": False}, "job": {}}

    def _save(self) -> None:
        _atomic_json(self.path, self.data)

    def start(self, operation_id: str, *, dataset: str) -> None:
        existing = self.data.get("operation_id")
        if existing not in {None, operation_id}:
            raise ValueError(f"journal belongs to another operation: {existing}")
        self.data.update(
            {"operation_id": operation_id, "dataset": dataset, "started_at": datetime.now(timezone.utc).isoformat()}
        )
        self._save()

    def begin_job(self, *, total_shards: int, resume: bool) -> None:
        self.data.setdefault("job", {}).update({"total_shards": int(total_shards), "resume": bool(resume),
                                                  "started_at": datetime.now(timezone.utc).isoformat()})
        self.data["control"] = {"pause_requested": False, "stop_requested": False}
        self._save()

    def request_pause(self, *, stop: bool = False) -> None:
        self.data.setdefault("control", {}).update({"pause_requested": True, "stop_requested": bool(stop),
                                                       "requested_at": datetime.now(timezone.utc).isoformat()})
        self._save()

    def paused(self) -> bool:
        return bool(self.data.get("control", {}).get("pause_requested"))

    def complete(self, unit: str, *, raw_sha256: str, row_count: int, **metadata: Any) -> None:
        if len(raw_sha256) != 64:
            raise ValueError("raw_sha256 must be a sha256 digest")
        self.data["units"][unit] = {
            "status": "COMPLETE", "raw_sha256": raw_sha256, "row_count": int(row_count), **metadata,
        }
        self._save()

    def running(self, unit: str) -> None:
        self.data["units"][unit] = {"status": "RUNNING", "updated_at": datetime.now(timezone.utc).isoformat()}
        self._save()

    def pending(self, unit: str, reason: str) -> None:
        self.data["units"][unit] = {"status": "PENDING", "reason": str(reason), "updated_at": datetime.now(timezone.utc).isoformat()}
        self._save()

    def gap(self, unit: str, status: str, reason: str) -> None:
        if status not in {"LEGAL_EMPTY", "NOT_COVERED"}:
            raise ValueError("gap status must be LEGAL_EMPTY or NOT_COVERED")
        self.data["units"][unit] = {"status": status, "reason": str(reason)}
        self._save()

    def heartbeat(self, *, phase: str, current_shard: str | None, pid: int) -> None:
        units = self.data["units"].values()
        self.data["heartbeat"] = {
            "job_id": self.data.get("operation_id"), "dataset": self.data.get("dataset"), "phase": phase,
            "pid": int(pid), "current_shard": current_shard,
            "completed": sum(row.get("status") == "COMPLETE" for row in units),
            "failed": sum(row.get("status") == "FAILED" for row in units),
            "legal_empty": sum(row.get("status") == "LEGAL_EMPTY" for row in units),
            "not_covered": sum(row.get("status") == "NOT_COVERED" for row in units),
            "skipped": sum(row.get("status") in {"LEGAL_EMPTY", "NOT_COVERED"} for row in units),
            "last_heartbeat": datetime.now(timezone.utc).isoformat(),
        }
        self._save()

    def record_probe(self, *, symbols: list[str], outcome: str, details: Any = None) -> None:
        self.data.setdefault("health_probes", []).append({"symbols": list(symbols), "outcome": outcome,
                                                            "details": details or {}, "at": datetime.now(timezone.utc).isoformat()})
        self._save()

    def phase(self, name: str, status: str) -> None:
        if status not in {"RUNNING", "DONE", "FAILED", "PAUSED"}:
            raise ValueError("phase status must be RUNNING, DONE, FAILED or PAUSED")
        self.data.setdefault("phases", {})[name] = {"status": status, "updated_at": datetime.now(timezone.utc).isoformat()}
        self._save()

    def fail(self, unit: str, error: str, **metadata: Any) -> None:
        self.data["units"][unit] = {"status": "FAILED", "error": str(error), **metadata}
        self._save()

    def classify_unclassified_symbol_errors(self) -> int:
        """Upgrade legacy SDK parse records without changing their shard result."""
        changed = 0
        for detail in self.data.get("units", {}).values():
            if detail.get("status") != "FAILED" or detail.get("category"):
                continue
            error = str(detail.get("error", ""))
            if "NoneType" in error or detail.get("exception_type") in {"TypeError", "KeyError", "AttributeError"}:
                detail["category"] = "SYMBOL_DATA_ERROR"
                detail.setdefault("raw_status", "UNAVAILABLE_SDK_EXCEPTION")
                changed += 1
        if changed:
            self._save()
        return changed

    def completed_units(self) -> set[str]:
        return {name for name, detail in self.data["units"].items() if detail["status"] == "COMPLETE"}

    def failed_units(self) -> dict[str, str]:
        return {name: detail["error"] for name, detail in self.data["units"].items() if detail["status"] == "FAILED"}

    def publish(self, release_id: str) -> None:
        if not str(release_id).strip():
            raise ValueError("release_id is required")
        self.data["published_release"] = release_id
        self.data["published_at"] = datetime.now(timezone.utc).isoformat()
        self._save()

    def published_release(self) -> str | None:
        value = self.data.get("published_release")
        return str(value) if value else None
