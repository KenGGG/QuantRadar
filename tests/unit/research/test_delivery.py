from datetime import date


def test_delivery_builds_digest_and_sends_an_outbox_once(tmp_path) -> None:
    from quantradar.research.config import ResearchSettings
    from quantradar.research.delivery import deliver_daily_digest
    from quantradar.research.storage import ResearchStore

    settings = ResearchSettings(f"sqlite+pysqlite:///{tmp_path / 'db.sqlite'}", tmp_path / "data", tmp_path / "profile", feishu_webhook_url="https://feishu.example/webhook", feishu_required_keyword="QUANTRADAR")
    store = ResearchStore(settings); store.create_schema()
    report = store.upsert_report({"source": "qyj", "source_report_id": "A" * 32, "title": "真实报告", "publish_date": date(2026, 8, 24), "content_type": "pdf", "source_payload": {}})
    store.save_analysis(report.id, "a" * 64, "profile", "model", {"research_type": "MARKET", "one_line_summary": "核心结论", "evidence": [{"chunk_id": "chunk-0001", "chunk_sha256": "hash"}]})
    sent = []

    def post(url, payload):
        sent.append((url, payload))
        return 200

    first = deliver_daily_digest(store, settings, date(2026, 8, 24), post=post)
    second = deliver_daily_digest(store, settings, date(2026, 8, 24), post=post)

    assert first.sent is True
    assert second.sent is False
    assert len(sent) == 1
    assert "QUANTRADAR" in sent[0][1]["content"]["text"]
