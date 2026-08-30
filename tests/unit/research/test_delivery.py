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


def test_versioned_digest_synthesizes_each_snapshot_channel_and_accounts_for_failures(tmp_path) -> None:
    from quantradar.research.config import ResearchSettings
    from quantradar.research.delivery import build_daily_digest
    from quantradar.research.storage import ResearchStore

    settings = ResearchSettings(f"sqlite+pysqlite:///{tmp_path / 'db.sqlite'}", tmp_path / "data", tmp_path / "profile")
    store = ResearchStore(settings); store.create_schema()
    target_date = date(2026, 8, 29)
    shared = store.upsert_report({"source":"qyj", "source_report_id":"D" * 32, "title":"跨栏目文章", "publish_date":target_date, "content_type":"pdf", "source_payload":{}})
    strategy = store.upsert_report({"source":"qyj", "source_report_id":"E" * 32, "title":"策略文章", "publish_date":target_date, "content_type":"pdf", "source_payload":{}})
    failed = store.upsert_report({"source":"qyj", "source_report_id":"F" * 32, "title":"待处理文章", "publish_date":target_date, "content_type":"pdf", "source_payload":{}})
    outside = store.upsert_report({"source":"qyj", "source_report_id":"G" * 32, "title":"不属于栏目", "publish_date":target_date, "content_type":"pdf", "source_payload":{}})
    store.record_snapshot(shared.id, target_date, "HOT", 2, "a" * 64)
    store.record_snapshot(failed.id, target_date, "HOT", 1, "b" * 64)
    store.record_snapshot(shared.id, target_date, "STRATEGY", 1, "c" * 64)
    store.record_snapshot(strategy.id, target_date, "STRATEGY", 2, "d" * 64)
    for report in (shared, strategy, outside):
        store.save_analysis(report.id, "m" * 63 + str(report.id), "profile-v3", "agnes", {
            "research_type":"MARKET", "one_line_summary":report.title, "key_points":["观点"],
            "core_conclusion":"结论", "method_or_logic":"not_supported", "risks_or_limitations":"not_supported",
            "evidence":[{"chunk_id":"chunk-1", "chunk_sha256":"h" * 64}],
        })

    class Synthesis:
        calls: list[dict] = []
        def complete(self, messages):
            self.calls.append(messages)
            return {"overall_summary":"栏目综述", "major_themes":["真实主题"], "important_views":"重要观点"}

    digest = build_daily_digest(store, target_date, Synthesis(), analysis_profile_hash="profile-v3", model="agnes")
    channels = digest.content_json["channels"]

    assert digest.content_json["digest_version"] == "yesterday-three-channel-v1"
    assert [item["channel"] for item in channels] == ["HOT", "STRATEGY", "FINANCIAL_ENGINEERING"]
    assert channels[0]["article_count"] == 2
    assert channels[0]["analyzed_count"] == 1
    assert channels[0]["failed_count"] == 1
    assert [item["title"] for item in channels[0]["article_index"]] == ["跨栏目文章"]
    assert [item["platform_order"] for item in channels[1]["article_index"]] == [1, 2]
    assert channels[1]["article_index"][0]["title"] == "跨栏目文章"
    assert len(Synthesis.calls) == 2
    assert digest.content_json["processing_exceptions"] == [{"title":"待处理文章", "channel":"HOT", "stage":"PENDING", "reason":"未找到当前分析版本"}]

    cached = build_daily_digest(store, target_date, Synthesis(), analysis_profile_hash="profile-v3", model="agnes")
    assert cached.digest_hash == digest.digest_hash
    assert len(Synthesis.calls) == 2


def test_channel_synthesis_normalizes_list_important_views() -> None:
    from quantradar.research.delivery import _synthesis

    class Synthesis:
        def complete(self, messages):
            return {
                "overall_summary": "栏目综述",
                "major_themes": ["真实主题"],
                "important_views": ["观点一", "观点二"],
            }

    result = _synthesis(Synthesis(), "HOT", "热门研报", [{"title": "真实文章"}])

    assert result["important_views"] == "- 观点一\n- 观点二"
