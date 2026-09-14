"""Pure contracts shared by the DataHub V3 index and financial datasets.

These helpers deliberately contain no network or database behaviour.  Keeping
the semantics here makes source audit, publication and release-pinned reads use
the same PIT rules.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


_SNAPSHOT_OBSERVATION_FIELDS = frozenset({"observed_at", "fetched_at", "raw_sha256"})


def snapshot_content_hash(rows: list[dict[str, Any]]) -> str:
    """Hash normalized business rows, independent of receipt metadata/order."""
    normalized = [
        {key: value for key, value in row.items() if key not in _SNAPSHOT_OBSERVATION_FIELDS}
        for row in rows
    ]
    payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    # Sorting serialized canonical rows makes source ordering immaterial while
    # retaining every business value, including a source-declared date.
    ordered = json.dumps(sorted(json.loads(payload), key=lambda row: json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(ordered.encode("utf-8")).hexdigest()


def snapshot_eligibility(
    snapshot: dict[str, Any], *, as_of: str | None = None, observed_before: str | None = None,
    strict_pit: bool = False,
) -> dict[str, Any]:
    """Apply the fixed distinction between market date and observation time."""
    source_date = snapshot.get("source_date")
    if as_of and (not source_date or str(source_date)[:10] > str(as_of)[:10]):
        return {"eligible": False, "reason": "SOURCE_DATE_UNKNOWN" if not source_date else "SOURCE_DATE_AFTER_AS_OF"}
    if observed_before and str(snapshot.get("observed_at") or "")[:10] > str(observed_before)[:10]:
        return {"eligible": False, "reason": "OBSERVED_AFTER_CUTOFF"}
    if strict_pit and (not source_date or snapshot.get("pit_status") != "PASS"):
        return {"eligible": False, "reason": "SOURCE_DATE_UNKNOWN" if not source_date else "PIT_NOT_QUALIFIED"}
    return {"eligible": True, "reason": "SOURCE_DATE_UNKNOWN" if not source_date else "QUALIFIED"}


def statement_mapping_identity(statement_version_id: str, mapping_version: str) -> tuple[str, str]:
    """Return the physical canonical-mapping identity; supplier versions never change."""
    if not str(statement_version_id).strip():
        raise ValueError("statement_version_id is required")
    if not str(mapping_version).strip():
        raise ValueError("mapping_version is required")
    return str(statement_version_id), str(mapping_version)
