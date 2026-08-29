"""Runtime safety primitives for unattended Research operations."""

from __future__ import annotations

import fcntl
import json
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4


def _redact(value):
    if isinstance(value, dict):
        return {key: ("[REDACTED]" if any(token in key.lower() for token in ("key", "secret", "token", "password")) else _redact(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def write_operation_record(data_dir: Path, operation: str, payload: dict) -> Path:
    directory = data_dir / "logs"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = directory / f"{operation}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex}.json"
    staging = destination.with_suffix(".part")
    staging.write_text(json.dumps(_redact(payload), ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    staging.replace(destination)
    return destination


class ResearchRunLock:
    def __init__(self, path: Path):
        self.path = path
        self._handle = None

    def acquire(self, *, blocking: bool = False) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError:
            self._handle.close(); self._handle = None
            return False
        return True

    def release(self) -> None:
        if self._handle is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close(); self._handle = None

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError("Research pipeline is already running")
        return self

    def __exit__(self, *_args) -> None:
        self.release()
