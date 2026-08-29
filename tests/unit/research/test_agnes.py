from quantradar.research.llm.chunking import SourceChunk


class FakeAgnesClient:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, messages):
        self.calls += 1
        return {"research_type": "MARKET", "one_line_summary": "结论", "evidence": [{"chunk_id": "chunk-0001", "chunk_sha256": "ok"}]}


def test_short_report_calls_client_once_and_validates_evidence() -> None:
    from quantradar.research.llm.agnes import AgnesAnalyzer

    client = FakeAgnesClient()
    result = AgnesAnalyzer(client).analyze_report("# 标题\n正文", [SourceChunk("chunk-0001", "# 标题\n正文", "ok")])

    assert result["one_line_summary"] == "结论"
    assert client.calls == 1
