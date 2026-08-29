"""Formal entry point for analyzing already-published MinerU Markdown only."""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from sqlalchemy import select

from .llm.agnes import AgnesAnalyzer, AgnesClient, TerminalAgnesError
from .llm.chunking import plan_chunks
from .llm.schemas import validate_analysis
from .models import ResearchAnalysis
from .storage import ResearchStore


ANALYSIS_PROMPT_VERSION = "prompt-v2"


def build_analysis_profile_hash(prompt_version: str, model_name: str, agnes_version: str, schema_version: str, chunking_version: str) -> str:
    payload = {"prompt_version": prompt_version, "model_name": model_name, "agnes_version": agnes_version, "schema_version": schema_version, "chunking_version": chunking_version}
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def analyze_markdown(store: ResearchStore, report_id: int, markdown: str, analysis_profile_hash: str, model: str, client: AgnesClient) -> ResearchAnalysis:
    if not markdown.strip():
        raise ValueError("Markdown is empty")
    markdown_sha256 = sha256(markdown.encode()).hexdigest()
    chunks = plan_chunks(markdown, max_chars=10000)
    with store._session() as session:
        existing = session.scalar(select(ResearchAnalysis).where(
            ResearchAnalysis.report_id == report_id,
            ResearchAnalysis.markdown_sha256 == markdown_sha256,
            ResearchAnalysis.analysis_profile_hash == analysis_profile_hash,
            ResearchAnalysis.status == "SUCCESS",
        ))
    if existing is not None and validate_analysis(existing.output_json, chunks, report_id=report_id, markdown_sha256=markdown_sha256).valid:
        return existing
    store.save_analysis_chunks(report_id, markdown_sha256, chunks)
    analyzer = AgnesAnalyzer(client)
    try:
        if len(chunks) == 1:
            result = analyzer.analyze_report(markdown, chunks, report_id=report_id, markdown_sha256=markdown_sha256)
        else:
            chunk_analyses = [
                analyzer.analyze_chunk(chunk, report_id=report_id, markdown_sha256=markdown_sha256)
                for chunk in chunks
            ]
            result = analyzer.synthesize_report(chunks, chunk_analyses, report_id=report_id, markdown_sha256=markdown_sha256)
    except Exception as exc:
        store.record_analysis_failure(report_id, markdown_sha256, analysis_profile_hash, model, exc, status="FAILED_TERMINAL" if isinstance(exc, TerminalAgnesError) else "FAILED_RETRYABLE")
        raise
    return store.save_analysis(report_id, markdown_sha256, analysis_profile_hash, model, result)
