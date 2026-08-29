"""Minimal structural validation for Agnes analysis output."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .chunking import SourceChunk


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: list[str]


def validate_analysis(analysis: dict[str, Any], chunks: list[SourceChunk], *, report_id: int | None = None, markdown_sha256: str | None = None) -> ValidationResult:
    known = {chunk.chunk_id: chunk.chunk_sha256 for chunk in chunks}
    errors = [f"ANALYSIS_MISSING_FIELD:{field}" for field in ("research_type", "one_line_summary") if not analysis.get(field)]
    if analysis.get("research_type") and analysis["research_type"] not in {"MARKET", "QUANT"}:
        errors.append("ANALYSIS_INVALID_RESEARCH_TYPE")
    for item in analysis.get("evidence", []):
        chunk_id = item.get("chunk_id")
        if chunk_id not in known:
            errors.append(f"EVIDENCE_MISSING_CHUNK:{chunk_id}")
        elif item.get("chunk_sha256") != known[chunk_id]:
            errors.append(f"EVIDENCE_HASH_MISMATCH:{chunk_id}")
        elif report_id is not None and (item.get("report_id") != report_id or item.get("markdown_sha256") != markdown_sha256):
            errors.append(f"EVIDENCE_SCOPE_MISMATCH:{chunk_id}")
    return ValidationResult(not errors, errors)
