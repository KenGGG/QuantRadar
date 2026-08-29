from datetime import date


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
            return {"research_type": "MARKET", "one_line_summary": "结论", "evidence": [{"chunk_id": "chunk-0001", "chunk_sha256": __import__("hashlib").sha256(messages[0]["content"].encode()).hexdigest()}]}

    client = Client()
    first = analyze_markdown(store, report.id, "正文", "profile", "model", client)
    second = analyze_markdown(store, report.id, "正文", "profile", "model", client)

    assert first.id == second.id
    assert client.calls == 1


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
            evidence = [{"chunk_id": "chunk-0001", "chunk_sha256": __import__("hashlib").sha256(text.split("\n\n")[0].encode()).hexdigest()}] if "\n\n" in text else []
            return {"research_type": "MARKET", "one_line_summary": "结论", "evidence": evidence}
    client = Client()
    analyze_markdown(store, report.id, "甲" * 10001 + "\n" + "乙" * 10001, "profile", "model", client)
    assert client.calls > 1
