from quantradar.research.llm.chunking import SourceChunk


def _digest_ready_fields() -> dict:
    return {
        "key_points": ["观点"], "core_conclusion": "结论", "method_or_logic": "not_supported",
        "risks_or_limitations": "not_supported",
    }


def test_analysis_rejects_evidence_for_a_missing_chunk() -> None:
    from quantradar.research.llm.schemas import validate_analysis

    result = validate_analysis(
        {"research_type": "MARKET", "one_line_summary": "结论", **_digest_ready_fields(), "evidence": [{"chunk_id": "chunk-9999"}]},
        [SourceChunk("chunk-0001", "原文")],
    )

    assert result.valid is False
    assert result.errors == ["EVIDENCE_MISSING_CHUNK:chunk-9999"]


def test_analysis_requires_digest_ready_report_fields() -> None:
    from quantradar.research.llm.chunking import SourceChunk
    from quantradar.research.llm.schemas import validate_analysis

    chunk = SourceChunk("chunk-0001", "正文", "hash", 1, 0, 2)

    result = validate_analysis({
        "research_type": "MARKET", "one_line_summary": "结论",
        "evidence": [{"chunk_id": "chunk-0001", "chunk_sha256": "hash"}],
    }, [chunk])

    assert result.errors == [
        "ANALYSIS_MISSING_FIELD:key_points",
        "ANALYSIS_MISSING_FIELD:core_conclusion",
        "ANALYSIS_MISSING_FIELD:method_or_logic",
        "ANALYSIS_MISSING_FIELD:risks_or_limitations",
    ]


def test_analysis_rejects_an_empty_evidence_list() -> None:
    from quantradar.research.llm.schemas import validate_analysis

    result = validate_analysis(
        {"research_type": "MARKET", "one_line_summary": "结论", **_digest_ready_fields(), "evidence": []},
        [SourceChunk("chunk-0001", "原文", "hash")],
    )

    assert result.errors == ["ANALYSIS_MISSING_EVIDENCE"]


def test_analysis_rejects_non_object_evidence_without_raising() -> None:
    from quantradar.research.llm.schemas import validate_analysis

    result = validate_analysis(
        {"research_type": "MARKET", "one_line_summary": "结论", **_digest_ready_fields(), "evidence": ["chunk-0001"]},
        [SourceChunk("chunk-0001", "原文", "hash")],
    )

    assert result.valid is False
    assert result.errors == ["EVIDENCE_INVALID_ITEM"]


def test_analysis_rejects_evidence_from_another_report_or_markdown_version() -> None:
    from quantradar.research.llm.schemas import validate_analysis

    result = validate_analysis(
        {"research_type": "MARKET", "one_line_summary": "结论", **_digest_ready_fields(), "evidence": [{"chunk_id": "chunk-0001", "chunk_sha256": "hash", "report_id": 9, "markdown_sha256": "old"}]},
        [SourceChunk("chunk-0001", "原文", "hash")],
        report_id=8,
        markdown_sha256="current",
    )

    assert result.errors == ["EVIDENCE_SCOPE_MISMATCH:chunk-0001"]


def test_analysis_requires_research_type_and_summary() -> None:
    from quantradar.research.llm.schemas import validate_analysis

    result = validate_analysis({"evidence": []}, [SourceChunk("chunk-0001", "原文", "hash")])

    assert result.errors == [
        "ANALYSIS_MISSING_FIELD:research_type", "ANALYSIS_MISSING_FIELD:one_line_summary",
        "ANALYSIS_MISSING_FIELD:key_points", "ANALYSIS_MISSING_FIELD:core_conclusion",
        "ANALYSIS_MISSING_FIELD:method_or_logic", "ANALYSIS_MISSING_FIELD:risks_or_limitations",
        "ANALYSIS_MISSING_EVIDENCE",
    ]
