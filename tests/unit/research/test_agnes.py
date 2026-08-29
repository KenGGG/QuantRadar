from quantradar.research.llm.chunking import SourceChunk
import httpx


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


def test_analyzer_supplies_a_structured_analysis_contract_before_markdown() -> None:
    from quantradar.research.llm.agnes import AgnesAnalyzer

    class CapturingClient:
        messages = None

        def complete(self, messages):
            self.messages = messages
            return {"research_type": "MARKET", "one_line_summary": "结论", "evidence": [{"chunk_id": "chunk-0001", "chunk_sha256": "ok"}]}

    client = CapturingClient()
    AgnesAnalyzer(client).analyze_report("# 标题\n正文", [SourceChunk("chunk-0001", "# 标题\n正文", "ok")])

    assert client.messages[0]["role"] == "system"
    assert "research_type" in client.messages[0]["content"]
    assert "one_line_summary" in client.messages[0]["content"]
    assert client.messages[1] == {"role": "user", "content": "# 标题\n正文"}


def test_analyzer_repairs_invalid_evidence_once_before_failing() -> None:
    from quantradar.research.llm.agnes import AgnesAnalyzer

    class RepairingClient:
        calls = 0
        repair_prompt = ""

        def complete(self, messages):
            self.calls += 1
            if self.calls == 1:
                return {"research_type": "MARKET", "one_line_summary": "结论", "evidence": [{"chunk_id": "wrong", "chunk_sha256": "wrong"}]}
            self.repair_prompt = messages[0]["content"]
            return {"research_type": "MARKET", "one_line_summary": "结论", "evidence": [{"chunk_id": "chunk-0001", "chunk_sha256": "ok"}]}

    client = RepairingClient()
    result = AgnesAnalyzer(client).analyze_report("正文", [SourceChunk("chunk-0001", "正文", "ok")])

    assert result["evidence"][0]["chunk_id"] == "chunk-0001"
    assert client.calls == 2
    assert "EVIDENCE_MISSING_CHUNK:wrong" in client.repair_prompt


def test_analyzer_canonicalizes_hash_for_a_known_evidence_chunk() -> None:
    from quantradar.research.llm.agnes import AgnesAnalyzer

    class HashMistypingClient:
        def complete(self, messages):
            return {"research_type": "MARKET", "one_line_summary": "结论", "evidence": [{"chunk_id": "chunk-0001", "chunk_sha256": "model-typo"}]}

    result = AgnesAnalyzer(HashMistypingClient()).analyze_report("正文", [SourceChunk("chunk-0001", "正文", "authoritative-hash")])

    assert result["evidence"] == [{"chunk_id": "chunk-0001", "chunk_sha256": "authoritative-hash"}]


def test_http_client_extracts_json_analysis_without_exposing_key() -> None:
    from quantradar.research.llm.agnes import AgnesHttpClient

    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"choices": [{"message": {"content": '{"research_type":"MARKET","evidence":[]}'}}]}))
    with httpx.Client(transport=transport) as session:
        result = AgnesHttpClient("https://agnes.example/v1", "secret", "model-x", session=session).complete([{"role": "user", "content": "正文"}])

    assert result == {"research_type": "MARKET", "evidence": []}


def test_http_client_marks_rate_limits_retryable() -> None:
    from quantradar.research.llm.agnes import AgnesHttpClient, RetryableAgnesError

    transport = httpx.MockTransport(lambda request: httpx.Response(429, json={"error": "rate limited"}))
    with httpx.Client(transport=transport) as session:
        client = AgnesHttpClient("https://agnes.example/v1", "secret", "model-x", session=session)
        try:
            client.complete([{"role": "user", "content": "正文"}])
        except RetryableAgnesError:
            return
    assert False, "rate limit must be retryable"


def test_http_client_accepts_a_long_report_read_timeout() -> None:
    from quantradar.research.llm.agnes import AgnesHttpClient

    client = AgnesHttpClient("https://agnes.example/v1", "secret", "model-x", timeout_seconds=180)
    try:
        assert client.session.timeout.read == 180
        assert client.session.timeout.connect == 10
    finally:
        client.session.close()


def test_http_client_spaces_requests_by_configured_rate_limit() -> None:
    from quantradar.research.llm.agnes import AgnesHttpClient

    clock = [0.0]
    sleeps = []
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"choices": [{"message": {"content": '{"research_type":"MARKET","evidence":[]}'}}]}))
    with httpx.Client(transport=transport) as session:
        client = AgnesHttpClient(
            "https://agnes.example/v1", "secret", "model-x", session=session,
            requests_per_minute=20, clock=lambda: clock[0], sleeper=lambda delay: sleeps.append(delay),
        )
        client.complete([{"role": "user", "content": "first"}])
        client.complete([{"role": "user", "content": "second"}])

    assert sleeps == [3.0]
