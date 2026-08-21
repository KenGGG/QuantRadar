from __future__ import annotations

import dataclasses
import datetime as dt
from decimal import Decimal
from enum import Enum
from typing import Any


class AuditStatus(str, Enum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    FAIL = "FAIL"


@dataclasses.dataclass(frozen=True)
class GateEvidence:
    status: AuditStatus
    ready: bool
    reasons: tuple[str, ...] = ()
    evidence_files: tuple[str, ...] = ()

    @classmethod
    def pass_(cls, *evidence_files: str) -> "GateEvidence":
        return cls(AuditStatus.PASS, True, evidence_files=tuple(evidence_files))

    @classmethod
    def partial(cls, reason: str, *evidence_files: str) -> "GateEvidence":
        return cls(
            AuditStatus.PARTIAL,
            False,
            reasons=(reason,),
            evidence_files=tuple(evidence_files),
        )

    @classmethod
    def blocked(cls, reason: str, *evidence_files: str) -> "GateEvidence":
        return cls(
            AuditStatus.BLOCKED,
            False,
            reasons=(reason,),
            evidence_files=tuple(evidence_files),
        )

    @classmethod
    def fail(cls, reason: str, *evidence_files: str) -> "GateEvidence":
        return cls(
            AuditStatus.FAIL,
            False,
            reasons=(reason,),
            evidence_files=tuple(evidence_files),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "ready": self.ready,
            "reasons": list(self.reasons),
            "evidence_files": list(self.evidence_files),
        }


def json_safe(value: Any) -> Any:
    """Convert database/Python values into deterministic JSON-compatible values."""
    if dataclasses.is_dataclass(value):
        return json_safe(dataclasses.asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return value

