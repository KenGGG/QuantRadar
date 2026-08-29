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
    known = {chunk.chunk_id for chunk in chunks}
    errors = [f"EVIDENCE_MISSING_CHUNK:{item.get('chunk_id')}" for item in analysis.get("evidence", []) if item.get("chunk_id") not in known]
    return ValidationResult(not errors, errors)
