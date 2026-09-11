"""Small durable DataHub work queues; no external scheduler is required."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .store import _atomic_json


QUEUES = ("current", "strategy", "historical")
TERMINAL = {"COMPLETE", "QUARANTINED", "BLOCKED"}


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
        if previous and previous.get("status") not in TERMINAL:
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
        data["tasks"][task_id] = record
        self._save(data)
        return {"status": "ENQUEUED", "task": record}

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

    def status(self) -> dict[str, Any]:
        data = self._load()
        counts = {queue: {state: 0 for state in ("PENDING", "RUNNING", *sorted(TERMINAL))} for queue in QUEUES}
        for task in data["tasks"].values():
            counts[task["queue"]].setdefault(task["status"], 0)
            counts[task["queue"]][task["status"]] += 1
        return {"counts": counts, "tasks": sorted(data["tasks"].values(), key=lambda item: (item["queue"], item["created_at"], item["task_id"]))}
