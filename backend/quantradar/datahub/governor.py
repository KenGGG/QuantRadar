"""Persistent, single-owner request control for DataHub source adapters."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import random
import time
from typing import Callable, Iterator, TypeVar


T = TypeVar("T")


class CircuitOpen(RuntimeError):
    """Raised before an upstream call when its persisted circuit is open."""


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


class RequestGovernor:
    """One retry owner, durable ledger, cooldown and cross-entry-point lock."""

    def __init__(
        self,
        root: Path | str,
        upstream: str,
        *,
        interval_seconds: float = 3.0,
        cooldown_seconds: float = 1800.0,
        failure_threshold: int = 3,
    ) -> None:
        if not upstream or "/" in upstream:
            raise ValueError("upstream must be a simple name")
        self.root = Path(root)
        self.upstream = upstream
        self.interval_seconds = max(0.0, interval_seconds)
        self.cooldown_seconds = max(1.0, cooldown_seconds)
        self.failure_threshold = max(1, failure_threshold)
        self.path = self.root / f"{upstream}.json"
        self.lock_path = self.root / f"{upstream}.lock"

    def _load(self) -> dict:
        if self.path.is_file():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return {
            "upstream": self.upstream,
            "logical_requests": 0,
            "actual_http_attempts": 0,
            "sdk_invocations": 0,
            "success": 0,
            "failure": 0,
            "retry": 0,
            "403": 0,
            "429": 0,
            "RemoteDisconnected": 0,
            "timeout": 0,
            "schema_invalid": 0,
            "symbol_data_error": 0,
            "circuit_open": False,
            "consecutive_failures": 0,
            "shard_failure_streak": 0,
            "upstream_failure_streak": 0,
            "consecutive_affected_symbols": [],
            "opened_on": None,
            "cooldown_until": None,
            "last_request_at": None,
            "last_error": None,
        }

    def status(self) -> dict:
        return self._load()

    def observed_status(self) -> dict:
        """Expose only counters visible outside an opaque public SDK."""
        ledger = self._load()
        return {
            **ledger,
            "sdk_attempts_opaque": int(ledger.get("sdk_invocations", 0)),
            "observed_http_attempts": int(ledger.get("actual_http_attempts", 0)),
            "observed_403": int(ledger.get("403", 0)),
            "observed_429": int(ledger.get("429", 0)),
            "observed_remote_disconnected": int(ledger.get("RemoteDisconnected", 0)),
            "observed_timeout": int(ledger.get("timeout", 0)),
        }

    def resolve_false_positive(self, *, symbol: str, reason: str) -> dict:
        """Clear an invalid local cooldown while retaining the original evidence."""
        ledger = self._load()
        ledger.setdefault("circuit_audit", []).append({
            "reason": reason, "original_symbol": symbol, "rate_limit_evidence": "none",
            "http_403": ledger.get("403", 0), "http_429": ledger.get("429", 0),
            "timeout": ledger.get("timeout", 0), "disconnect": ledger.get("RemoteDisconnected", 0),
            "resolved_at": self._now().isoformat(), "action": "cooldown_cleared_after_code_fix",
        })
        ledger.update({"circuit_open": False, "cooldown_until": None, "consecutive_failures": 0,
                       "shard_failure_streak": 0, "upstream_failure_streak": 0,
                       "consecutive_affected_symbols": []})
        _atomic_json(self.path, ledger)
        return ledger

    @contextmanager
    def operation_lock(self) -> Iterator[None]:
        """Hold the upstream lock across an entire extract operation."""
        self.root.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise CircuitOpen(f"{self.upstream} is already owned by another DataHub operation") from exc
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _kind(exc: Exception) -> str:
        if type(exc).__name__ == "AdapterParseError":
            return "symbol_data_error"
        message = f"{type(exc).__name__}: {exc}".lower()
        if "429" in message:
            return "429"
        if "403" in message:
            return "403"
        if "schema" in message:
            return "schema_invalid"
        if "remote" in message and "disconnect" in message:
            return "RemoteDisconnected"
        if "timeout" in message:
            return "timeout"
        return "failure"

    @staticmethod
    def _category(kind: str) -> str:
        if kind in {"403", "429"}:
            return "RATE_LIMIT_OR_BLOCK"
        if kind in {"timeout", "RemoteDisconnected"}:
            return "TRANSIENT_NETWORK_ERROR"
        return "SYMBOL_DATA_ERROR"

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _ensure_closed(self, ledger: dict) -> None:
        if not ledger.get("circuit_open"):
            return
        deadline = ledger.get("cooldown_until")
        if deadline and self._now() >= datetime.fromisoformat(deadline):
            ledger["circuit_open"] = False
            ledger["consecutive_failures"] = 0
            _atomic_json(self.path, ledger)
            return
        raise CircuitOpen(f"{self.upstream} circuit open until {deadline}")

    def _open(self, ledger: dict) -> None:
        now = self._now()
        today = now.date().isoformat()
        if ledger.get("opened_on") == today:
            cooldown = now + timedelta(days=1)
        else:
            cooldown = now + timedelta(seconds=self.cooldown_seconds)
        ledger.update({"circuit_open": True, "opened_on": today, "cooldown_until": cooldown.isoformat()})

    def call(
        self, logical_key: str, operation: Callable[[], T], *, max_attempts: int = 2, http_attempts_known: bool = True
    ) -> T:
        """Run one logical request; SDK-owned retries require ``max_attempts=1``."""
        if not logical_key:
            raise ValueError("logical_key is required")
        if max_attempts not in {1, 2}:
            raise ValueError("max_attempts must be one or two")
        ledger = self._load()
        for key, default in (("shard_failure_streak", 0), ("upstream_failure_streak", 0),
                             ("consecutive_affected_symbols", []), ("symbol_data_error", 0)):
            ledger.setdefault(key, default)
        self._ensure_closed(ledger)
        ledger["logical_requests"] += 1
        for attempt in range(max_attempts):
            last = ledger.get("last_request_at")
            if last:
                elapsed = (self._now() - datetime.fromisoformat(last)).total_seconds()
                if elapsed < self.interval_seconds:
                    time.sleep(self.interval_seconds - elapsed + random.uniform(0, 0.25))
            if http_attempts_known:
                ledger["actual_http_attempts"] += 1
            else:
                ledger["sdk_invocations"] = int(ledger.get("sdk_invocations", 0)) + 1
            ledger["last_request_at"] = self._now().isoformat()
            try:
                result = operation()
            except Exception as exc:
                kind = self._kind(exc)
                category = self._category(kind)
                symbol = logical_key.rsplit("/", 1)[-1]
                ledger["last_error"] = {"symbol": symbol, "category": category, "kind": kind,
                                        "message": str(exc), "at": self._now().isoformat(), "logical_key": logical_key}
                ledger[kind] = int(ledger.get(kind, 0)) + 1
                immediate_open = kind in {"403", "429"}
                if immediate_open or attempt + 1 == max_attempts:
                    ledger["failure"] += 1
                    if category == "SYMBOL_DATA_ERROR":
                        ledger["shard_failure_streak"] = 1
                    else:
                        affected = list(ledger.get("consecutive_affected_symbols") or [])
                        if not affected or affected[-1] != symbol:
                            affected.append(symbol)
                        ledger["consecutive_affected_symbols"] = affected
                        ledger["upstream_failure_streak"] = len(affected)
                    ledger["consecutive_failures"] = ledger["upstream_failure_streak"]
                    if immediate_open or (category == "TRANSIENT_NETWORK_ERROR" and ledger["upstream_failure_streak"] >= self.failure_threshold):
                        self._open(ledger)
                    _atomic_json(self.path, ledger)
                    raise
                ledger["retry"] += 1
                _atomic_json(self.path, ledger)
                continue
            ledger["success"] += 1
            ledger["consecutive_failures"] = 0
            ledger["shard_failure_streak"] = 0
            ledger["upstream_failure_streak"] = 0
            ledger["consecutive_affected_symbols"] = []
            ledger["last_error"] = None
            _atomic_json(self.path, ledger)
            return result
        raise AssertionError("unreachable")
