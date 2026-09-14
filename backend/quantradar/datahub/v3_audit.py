"""G0 source-audit receipts for DataHub V3.

The audit captures exactly what an adapter returned.  It intentionally does
not upgrade an historical value into a strict PIT fact.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from typing import Any

from .store import RawStore


def record_probe(
    raw_store: RawStore, *, dataset: str, source: str, request: dict[str, Any], rows: list[dict[str, Any]],
    observed_at: str, adapter_version: str,
) -> dict[str, Any]:
    """Persist a deterministic source receipt and return its evidence manifest."""
    content = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    raw = raw_store.put(f"v3-g0/{dataset}", content)
    columns = sorted({str(column) for row in rows for column in row})
    return {
        "dataset": dataset,
        "source": source,
        "request": request,
        "observed_at": observed_at,
        "adapter_version": adapter_version,
        "raw_sha256": raw["sha256"],
        "raw_bytes": raw["bytes"],
        "row_count": len(rows),
        "schema": {"columns": columns},
        "qualification": "RAW_EVIDENCE_ONLY",
        "pit_status": "PARTIAL",
    }


def run_probes(
    raw_store: RawStore,
    probes: Iterable[tuple[str, str, dict[str, Any], Callable[[], list[dict[str, Any]]]]], *,
    observed_at: str, adapter_version: str,
) -> dict[str, Any]:
    """Run independent bounded probes without concealing individual failures."""
    receipts, failures = [], []
    for dataset, source, request, fetch in probes:
        try:
            receipts.append(record_probe(
                raw_store, dataset=dataset, source=source, request=request,
                rows=fetch(), observed_at=observed_at, adapter_version=adapter_version,
            ))
        except Exception as exc:
            failures.append({
                "dataset": dataset, "request": request,
                "error_type": type(exc).__name__, "error": str(exc),
            })
    return {
        "gate": "G0", "observed_at": observed_at, "adapter_version": adapter_version,
        "receipts": receipts, "failures": failures,
        "status": "PASS" if receipts and not failures else "PARTIAL",
    }
