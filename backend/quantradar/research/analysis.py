"""Formal entry point for analyzing already-published MinerU Markdown only."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from sqlalchemy import select

from .llm.agnes import AgnesAnalyzer, AgnesClient
from .llm.chunking import plan_chunks
from .models import ResearchAnalysis
from .storage import ResearchStore


def analyze_markdown(store: ResearchStore, report_id: int, markdown: str, analysis_profile_hash: str, model: str, client: AgnesClient) -> ResearchAnalysis:
    if not markdown.strip():
        raise ValueError("Markdown is empty")
    markdown_sha256 = sha256(markdown.encode()).hexdigest()
    with store._session() as session:
        existing = session.scalar(select(ResearchAnalysis).where(
            ResearchAnalysis.report_id == report_id,
            ResearchAnalysis.markdown_sha256 == markdown_sha256,
            ResearchAnalysis.analysis_profile_hash == analysis_profile_hash,
            ResearchAnalysis.status == "SUCCESS",
        ))
    if existing is not None:
        return existing
    chunks = plan_chunks(markdown, max_chars=10000)
    analyzer = AgnesAnalyzer(client)
    if len(chunks) == 1:
        result = analyzer.analyze_report(markdown, chunks)
    else:
        for chunk in chunks:
            analyzer.analyze_chunk(chunk)
        result = analyzer.synthesize_report(chunks)
    return store.save_analysis(report_id, markdown_sha256, analysis_profile_hash, model, result)
