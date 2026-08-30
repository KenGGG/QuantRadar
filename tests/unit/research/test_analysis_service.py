from datetime import date
import re


def _analysis(summary: str, evidence: list[dict]) -> dict:
    return {"research_type": "MARKET", "one_line_summary": summary, "key_points": [summary], "core_conclusion": summary, "method_or_logic": "not_supported", "risks_or_limitations": "not_supported", "evidence": evidence}


def test_existing_markdown_is_analyzed_once_and_persisted(tmp_path) -> None:
    from quantradar.research.analysis import analyze_markdown
    from quantradar.research.config import ResearchSettings
    from quantradar.research.storage import ResearchStore

    settings = ResearchSettings(database_url=f"sqlite+pysqlite:///{tmp_path / 'db.sqlite'}", data_dir=tmp_path / "data", qyj_profile_dir=tmp_path / "profile")
    store = ResearchStore(settings); store.create_schema()
    report = store.upsert_report({"source": "qyj", "source_report_id": "r1", "title": "标题", "publish_date": date(2026, 8, 1), "content_type": "pdf", "source_payload": {}})

    class Client:
        calls = 0
        def complete(self, messages):
            self.calls += 1
            return _analysis("结论", [{"chunk_id": "chunk-0001", "chunk_sha256": __import__("hashlib").sha256(messages[-1]["content"].encode()).hexdigest()}])

    client = Client()
    first = analyze_markdown(store, report.id, "正文", "profile", "model", client)
    second = analyze_markdown(store, report.id, "正文", "profile", "model", client)

    assert first.id == second.id
    assert client.calls == 1


def test_analysis_reanalyzes_a_legacy_success_without_evidence(tmp_path) -> None:
    from quantradar.research.analysis import analyze_markdown
    from quantradar.research.config import ResearchSettings
    from quantradar.research.storage import ResearchStore

    settings = ResearchSettings(database_url=f"sqlite+pysqlite:///{tmp_path / 'db.sqlite'}", data_dir=tmp_path / "data", qyj_profile_dir=tmp_path / "profile")
    store = ResearchStore(settings); store.create_schema()
    report = store.upsert_report({"source": "qyj", "source_report_id": "legacy", "title": "旧结果", "publish_date": date(2026, 8, 1), "content_type": "pdf", "source_payload": {}})
    markdown = "正文"
    markdown_sha256 = __import__("hashlib").sha256(markdown.encode()).hexdigest()
    store.save_analysis(report.id, markdown_sha256, "profile", "model", {"research_type": "MARKET", "one_line_summary": "旧结论", "evidence": []})

    class Client:
        calls = 0
        def complete(self, messages):
            self.calls += 1
            return _analysis("新结论", [{"chunk_id": "chunk-0001", "chunk_sha256": "ignored"}])

    client = Client()
    result = analyze_markdown(store, report.id, markdown, "profile", "model", client)

    assert client.calls == 1
    assert result.output_json["one_line_summary"] == "新结论"


def test_long_markdown_analyzes_each_chunk_before_synthesis(tmp_path) -> None:
    from quantradar.research.analysis import analyze_markdown
    from quantradar.research.config import ResearchSettings
    from quantradar.research.storage import ResearchStore
    settings = ResearchSettings(database_url=f"sqlite+pysqlite:///{tmp_path / 'db.sqlite'}", data_dir=tmp_path / "data", qyj_profile_dir=tmp_path / "profile")
    store = ResearchStore(settings); store.create_schema()
    report = store.upsert_report({"source": "qyj", "source_report_id": "r2", "title": "长报告", "publish_date": date(2026, 8, 1), "content_type": "pdf", "source_payload": {}})
    class Client:
        calls = 0
        def complete(self, messages):
            self.calls += 1
            text = messages[0]["content"]
            chunk_id = re.search(r'"chunk_id": "(chunk-\d+)"', text).group(1)
            evidence = [{"chunk_id": chunk_id, "chunk_sha256": "test-hash"}]
            return _analysis("结论", evidence)
    client = Client()
    analyze_markdown(store, report.id, "甲" * 10001 + "\n" + "乙" * 10001, "profile", "model", client)
    assert client.calls > 1


def test_long_report_synthesis_receives_chunk_analyses(tmp_path) -> None:
    from quantradar.research.analysis import analyze_markdown
    from quantradar.research.config import ResearchSettings
    from quantradar.research.storage import ResearchStore

    settings = ResearchSettings(database_url=f"sqlite+pysqlite:///{tmp_path / 'db.sqlite'}", data_dir=tmp_path / "data", qyj_profile_dir=tmp_path / "profile")
    store = ResearchStore(settings); store.create_schema()
    report = store.upsert_report({"source": "qyj", "source_report_id": "r5", "title": "长报告", "publish_date": date(2026, 8, 1), "content_type": "pdf", "source_payload": {}})

    class Client:
        messages: list[list[dict]] = []
        def complete(self, messages):
            self.messages.append(messages)
            text = messages[-1]["content"]
            if "chunk_analyses" in text:
                return _analysis("综合结论", [{"chunk_id": "chunk-0001", "chunk_sha256": __import__("hashlib").sha256(("甲" * 10000).encode()).hexdigest()}])
            chunk_id = re.search(r'"chunk_id": "(chunk-\d+)"', messages[0]["content"]).group(1)
            return _analysis("分块结论", [{"chunk_id": chunk_id, "chunk_sha256": "test-hash"}])

    client = Client()
    analyze_markdown(store, report.id, "甲" * 10001 + "\n" + "乙" * 10001, "profile", "model", client)
    assert "chunk_analyses" in client.messages[-1][-1]["content"]


def test_failed_analysis_is_recorded_and_the_same_version_can_retry(tmp_path) -> None:
    from quantradar.research.analysis import analyze_markdown
    from quantradar.research.config import ResearchSettings
    from quantradar.research.storage import ResearchStore
    settings = ResearchSettings(database_url=f"sqlite+pysqlite:///{tmp_path / 'db.sqlite'}", data_dir=tmp_path / "data", qyj_profile_dir=tmp_path / "profile")
    store = ResearchStore(settings); store.create_schema()
    report = store.upsert_report({"source": "qyj", "source_report_id": "r3", "title": "失败重试", "publish_date": date(2026, 8, 1), "content_type": "pdf", "source_payload": {}})
    class Broken:
        def complete(self, _messages): raise TimeoutError("timeout")
    class Good:
        def complete(self, messages): return _analysis("结论", [{"chunk_id": "chunk-0001", "chunk_sha256": __import__("hashlib").sha256(messages[-1]["content"].encode()).hexdigest()}])
    try:
        analyze_markdown(store, report.id, "正文", "profile", "model", Broken())
    except TimeoutError:
        pass
    failed = store.latest_analysis(report.id, "profile")
    assert failed.status == "FAILED_RETRYABLE"
    recovered = analyze_markdown(store, report.id, "正文", "profile", "model", Good())
    assert recovered.id == failed.id
    assert recovered.status == "SUCCESS"


def test_profile_hash_changes_when_model_or_prompt_changes() -> None:
    from quantradar.research.analysis import ANALYSIS_PROMPT_VERSION, build_analysis_profile_hash

    baseline = build_analysis_profile_hash("prompt-v1", "model-a", "agnes-http-v1", "schema-v1", "chunking-v1")

    assert baseline != build_analysis_profile_hash("prompt-v2", "model-a", "agnes-http-v1", "schema-v1", "chunking-v1")
    assert baseline != build_analysis_profile_hash("prompt-v1", "model-b", "agnes-http-v1", "schema-v1", "chunking-v1")
    assert ANALYSIS_PROMPT_VERSION == "prompt-v4-multiformat-canonical"


def test_terminal_agnes_error_is_not_marked_retryable(tmp_path) -> None:
    from quantradar.research.analysis import analyze_markdown
    from quantradar.research.config import ResearchSettings
    from quantradar.research.llm.agnes import TerminalAgnesError
    from quantradar.research.storage import ResearchStore
    settings = ResearchSettings(database_url=f"sqlite+pysqlite:///{tmp_path / 'db.sqlite'}", data_dir=tmp_path / "data", qyj_profile_dir=tmp_path / "profile")
    store = ResearchStore(settings); store.create_schema()
    report = store.upsert_report({"source": "qyj", "source_report_id": "r4", "title": "终止失败", "publish_date": date(2026, 8, 1), "content_type": "pdf", "source_payload": {}})
    class Broken:
        def complete(self, _messages): raise TerminalAgnesError("HTTP_401")
    try: analyze_markdown(store, report.id, "正文", "profile", "model", Broken())
    except TerminalAgnesError: pass
    assert store.latest_analysis(report.id, "profile").status == "FAILED_TERMINAL"
