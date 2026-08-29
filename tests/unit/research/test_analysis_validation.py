from quantradar.research.llm.chunking import SourceChunk


def test_analysis_rejects_evidence_for_a_missing_chunk() -> None:
    from quantradar.research.llm.schemas import validate_analysis

    result = validate_analysis(
        {"research_type": "MARKET", "one_line_summary": "结论", "evidence": [{"chunk_id": "chunk-9999"}]},
        [SourceChunk("chunk-0001", "原文")],
    )

    assert result.valid is False
    assert result.errors == ["EVIDENCE_MISSING_CHUNK:chunk-9999"]


def test_analysis_rejects_an_empty_evidence_list() -> None:
    from quantradar.research.llm.schemas import validate_analysis

    result = validate_analysis(
        {"research_type": "MARKET", "one_line_summary": "结论", "evidence": []},
        [SourceChunk("chunk-0001", "原文", "hash")],
    )

    assert result.errors == ["ANALYSIS_MISSING_EVIDENCE"]


def test_analysis_rejects_evidence_from_another_report_or_markdown_version() -> None:
    from quantradar.research.llm.schemas import validate_analysis

    result = validate_analysis(
        {"research_type": "MARKET", "one_line_summary": "结论", "evidence": [{"chunk_id": "chunk-0001", "chunk_sha256": "hash", "report_id": 9, "markdown_sha256": "old"}]},
        [SourceChunk("chunk-0001", "原文", "hash")],
        report_id=8,
        markdown_sha256="current",
    )

    assert result.errors == ["EVIDENCE_SCOPE_MISMATCH:chunk-0001"]


def test_analysis_requires_research_type_and_summary() -> None:
    from quantradar.research.llm.schemas import validate_analysis

    result = validate_analysis({"evidence": []}, [SourceChunk("chunk-0001", "原文", "hash")])

    assert result.errors == ["ANALYSIS_MISSING_FIELD:research_type", "ANALYSIS_MISSING_FIELD:one_line_summary", "ANALYSIS_MISSING_EVIDENCE"]
