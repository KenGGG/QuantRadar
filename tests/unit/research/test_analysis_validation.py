from quantradar.research.llm.chunking import SourceChunk


def test_analysis_rejects_evidence_for_a_missing_chunk() -> None:
    from quantradar.research.llm.schemas import validate_analysis

    result = validate_analysis(
        {"research_type": "MARKET", "one_line_summary": "结论", "evidence": [{"chunk_id": "chunk-9999"}]},
        [SourceChunk("chunk-0001", "原文")],
    )

    assert result.valid is False
    assert result.errors == ["EVIDENCE_MISSING_CHUNK:chunk-9999"]
