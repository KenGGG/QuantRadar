"""Minimal structural validation for Agnes analysis output."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .chunking import SourceChunk


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: list[str]


def validate_analysis(analysis: dict[str, Any], chunks: list[SourceChunk]) -> ValidationResult:
    known = {chunk.chunk_id: chunk.chunk_sha256 for chunk in chunks}
    errors = []
    for item in analysis.get("evidence", []):
        chunk_id = item.get("chunk_id")
        if chunk_id not in known:
            errors.append(f"EVIDENCE_MISSING_CHUNK:{chunk_id}")
        elif item.get("chunk_sha256") != known[chunk_id]:
            errors.append(f"EVIDENCE_HASH_MISMATCH:{chunk_id}")
    return ValidationResult(not errors, errors)
