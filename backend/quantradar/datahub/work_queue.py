"""Small durable DataHub work queues; no external scheduler is required."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .store import _atomic_json


QUEUES = ("current", "strategy", "historical")
TERMINAL = {"COMPLETE", "QUARANTINED", "BLOCKED", "SATISFIED", "OBSOLETE"}


class DataHubWorkQueue:
    """Persisted, round-robin work orders with a semantic idempotency key."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _load(self) -> dict[str, Any]:
        if self.path.is_file():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return {"version": 1, "dispatch_cursor": -1, "tasks": {}}

    def _save(self, data: dict[str, Any]) -> None:
        _atomic_json(self.path, data)

    @staticmethod
    def _identity(queue: str, task: dict[str, Any]) -> str:
        semantic = {key: task.get(key) for key in (
            "source_contract_id", "domain", "fields", "symbols", "range", "gap_reason", "gap_fingerprint",
        )}
        return hashlib.sha256((queue + "\0" + json.dumps(semantic, ensure_ascii=False, sort_keys=True)).encode()).hexdigest()[:24]

    @staticmethod
    def _overlaps(left: dict[str, Any], right: dict[str, Any]) -> bool:
        return str(left["start"]) <= str(right["end"]) and str(right["start"]) <= str(left["end"])

    @classmethod
    def _supersede_current_overlap(cls, data: dict[str, Any], record: dict[str, Any], now: str) -> None:
        """A new rolling correction window replaces older overlapping checks."""
        if record["queue"] != "current":
            return
        for old_id, old in data["tasks"].items():
            if old_id == record["task_id"] or old.get("queue") != "current" or old.get("status") != "PENDING":
                continue
            if (old.get("domain"), old.get("symbols"), old.get("fields"), old.get("expected_key_contract")) != (
                record.get("domain"), record.get("symbols"), record.get("fields"), record.get("expected_key_contract"),
            ):
                continue
            if cls._overlaps(old["range"], record["range"]):
                old.update(status="OBSOLETE", updated_at=now, superseded_by=record["task_id"],
                           resolution="newer rolling correction window supersedes overlapping pending check")

    def enqueue(self, queue: str, task: dict[str, Any]) -> dict[str, Any]:
        if queue not in QUEUES:
            raise ValueError(f"unknown queue: {queue}")
        required = {"source_contract_id", "domain", "range", "gap_reason", "gap_fingerprint"}
        missing = sorted(key for key in required if not task.get(key))
        if missing:
            raise ValueError("work order missing: " + ", ".join(missing))
        task_id = self._identity(queue, task)
        data = self._load()
        previous = data["tasks"].get(task_id)
        # A task identity is an audit record, not a request to retry a result.
        # A changed gap/contract produces a different identity; terminal work is
        # never silently resurrected by the daily planner.
        if previous:
            return {"status": "NO_CHANGE", "task": previous}
        now = datetime.now(timezone.utc).isoformat()
        record = {
            **task, "task_id": task_id, "queue": queue, "status": "PENDING",
            "created_at": previous.get("created_at", now) if previous else now,
            "updated_at": now, "attempts": int(previous.get("attempts", 0)) if previous else 0,
        }
        # A changed source contract or repair fingerprint is a new task.  The
        # older pending plan remains auditable but must not race it later.
        for old_id, old in data["tasks"].items():
            if old_id == task_id or old.get("status") != "PENDING" or old.get("queue") != queue:
                continue
            if all(old.get(key) == record.get(key) for key in ("domain", "range", "gap_fingerprint")):
                old.update(status="BLOCKED", updated_at=now, superseded_by=task_id,
                           resolution="source contract or task definition changed before dispatch")
        self._supersede_current_overlap(data, record, now)
        data["tasks"][task_id] = record
        self._save(data)
        return {"status": "ENQUEUED", "task": record}

    def enqueue_many(self, queue: str, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Persist a large deterministic plan with one load and one atomic save."""
        if queue not in QUEUES:
            raise ValueError(f"unknown queue: {queue}")
        data, outcomes = self._load(), []
        now = datetime.now(timezone.utc).isoformat()
        for task in tasks:
            required = {"source_contract_id", "domain", "range", "gap_reason", "gap_fingerprint"}
            missing = sorted(key for key in required if not task.get(key))
            if missing:
                raise ValueError("work order missing: " + ", ".join(missing))
            task_id = self._identity(queue, task)
            previous = data["tasks"].get(task_id)
            if previous:
                outcomes.append({"status": "NO_CHANGE", "task": previous})
                continue
            record = {**task, "task_id": task_id, "queue": queue, "status": "PENDING",
                      "created_at": previous.get("created_at", now) if previous else now, "updated_at": now,
                      "attempts": int(previous.get("attempts", 0)) if previous else 0}
            self._supersede_current_overlap(data, record, now)
            data["tasks"][task_id] = record
            outcomes.append({"status": "ENQUEUED", "task": record})
        self._save(data)
        return outcomes

    def claim_next(self) -> dict[str, Any] | None:
        """Rotate queues so current updates cannot starve historical repair."""
        data = self._load()
        start = (int(data.get("dispatch_cursor", -1)) + 1) % len(QUEUES)
        for offset in range(len(QUEUES)):
            queue_index = (start + offset) % len(QUEUES)
            queue = QUEUES[queue_index]
            candidates = sorted(
                (task for task in data["tasks"].values() if task.get("queue") == queue and task.get("status") == "PENDING"),
                key=lambda task: (task.get("created_at", ""), task["task_id"]),
            )
            if not candidates:
                continue
            task = candidates[0]
            task.update(status="RUNNING", attempts=int(task.get("attempts", 0)) + 1,
                        updated_at=datetime.now(timezone.utc).isoformat())
            data["dispatch_cursor"] = queue_index
            self._save(data)
            return dict(task)
        return None

    def claim_next_from(self, queue: str) -> dict[str, Any] | None:
        """Claim only one named queue; used by domain-specific workers."""
        if queue not in QUEUES:
            raise ValueError(f"unknown queue: {queue}")
        data = self._load()
        candidates = sorted((task for task in data["tasks"].values() if task.get("queue") == queue and task.get("status") == "PENDING"),
                            key=lambda task: (task.get("created_at", ""), task["task_id"]))
        if not candidates:
            return None
        task = candidates[0]
        task.update(status="RUNNING", attempts=int(task.get("attempts", 0)) + 1,
                    updated_at=datetime.now(timezone.utc).isoformat())
        self._save(data)
        return dict(task)

    def claim_matching(self, queue: str, *, domain: str, limit: int) -> list[dict[str, Any]]:
        """Claim a bounded homogeneous batch without consuming other work."""
        if queue not in QUEUES:
            raise ValueError(f"unknown queue: {queue}")
        if limit < 1:
            raise ValueError("limit must be positive")
        data = self._load()
        candidates = sorted(
            (task for task in data["tasks"].values()
             if task.get("queue") == queue and task.get("status") == "PENDING" and task.get("domain") == domain),
            key=lambda task: (task.get("created_at", ""), task["task_id"]),
        )[:limit]
        now = datetime.now(timezone.utc).isoformat()
        for task in candidates:
            task.update(status="RUNNING", attempts=int(task.get("attempts", 0)) + 1, updated_at=now)
        if candidates:
            self._save(data)
        return [dict(task) for task in candidates]

    def recover_running(self, queue: str, *, domain: str, evidence: dict[str, Any]) -> int:
        """Return abandoned domain work to pending before its next exclusive run."""
        if queue not in QUEUES:
            raise ValueError(f"unknown queue: {queue}")
        data = self._load()
        tasks = [task for task in data["tasks"].values()
                 if task.get("queue") == queue and task.get("domain") == domain and task.get("status") == "RUNNING"]
        for task in tasks:
            task.update(status="PENDING", updated_at=datetime.now(timezone.utc).isoformat(), re_audit=evidence)
        if tasks:
            self._save(data)
        return len(tasks)

    def finish(self, task_id: str, status: str, *, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
        """Persist a terminal outcome; retryability stays explicit in the task."""
        if status not in TERMINAL:
            raise ValueError(f"terminal status required: {status}")
        data = self._load()
        task = data["tasks"].get(task_id)
        if task is None:
            raise KeyError(task_id)
        if task.get("status") in TERMINAL:
            return {"status": "NO_CHANGE", "task": task}
        task.update(status=status, updated_at=datetime.now(timezone.utc).isoformat(), evidence=evidence or {})
        self._save(data)
        return {"status": status, "task": task}

    def defer(self, task_id: str, *, evidence: dict[str, Any], release_id: str | None = None) -> dict[str, Any]:
        """Return a re-audited task to pending without losing its audit trail."""
        data = self._load()
        task = data["tasks"].get(task_id)
        if task is None:
            raise KeyError(task_id)
        if task.get("status") != "RUNNING":
            raise ValueError("only a running task can be deferred")
        task.update(status="PENDING", updated_at=datetime.now(timezone.utc).isoformat(), re_audit=evidence)
        if release_id is not None:
            task["release_id"] = release_id
        self._save(data)
        return {"status": "PENDING", "task": task}

    def status(self) -> dict[str, Any]:
        data = self._load()
        counts = {queue: {state: 0 for state in ("PENDING", "RUNNING", *sorted(TERMINAL))} for queue in QUEUES}
        for task in data["tasks"].values():
            counts[task["queue"]].setdefault(task["status"], 0)
            counts[task["queue"]][task["status"]] += 1
        return {"counts": counts, "tasks": sorted(data["tasks"].values(), key=lambda item: (item["queue"], item["created_at"], item["task_id"]))}
