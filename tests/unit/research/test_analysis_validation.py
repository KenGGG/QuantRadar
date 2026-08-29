from quantradar.research.llm.chunking import SourceChunk


def test_analysis_rejects_evidence_for_a_missing_chunk() -> None:
    from quantradar.research.llm.schemas import validate_analysis

    result = validate_analysis(
        {"research_type": "MARKET", "one_line_summary": "结论", "evidence": [{"chunk_id": "chunk-9999"}]},
        [SourceChunk("chunk-0001", "原文")],
    )

    assert result.valid is False
    assert result.errors == ["EVIDENCE_MISSING_CHUNK:chunk-9999"]


def test_analysis_rejects_evidence_from_another_report_or_markdown_version() -> None:
    from quantradar.research.llm.schemas import validate_analysis

    result = validate_analysis(
        {"evidence": [{"chunk_id": "chunk-0001", "chunk_sha256": "hash", "report_id": 9, "markdown_sha256": "old"}]},
        [SourceChunk("chunk-0001", "原文", "hash")],
        report_id=8,
        markdown_sha256="current",
    )

    assert result.errors == ["EVIDENCE_SCOPE_MISMATCH:chunk-0001"]
