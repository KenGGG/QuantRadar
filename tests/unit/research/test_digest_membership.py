from datetime import date


def test_digest_membership_uses_snapshot_channel_and_platform_order(tmp_path) -> None:
    from quantradar.research.config import ResearchSettings
    from quantradar.research.storage import ResearchStore

    settings = ResearchSettings(f"sqlite+pysqlite:///{tmp_path / 'research.db'}", tmp_path / "data", tmp_path / "profile")
    store = ResearchStore(settings); store.create_schema()
    target_date = date(2026, 8, 29)
    first = store.upsert_report({"source":"qyj", "source_report_id":"A" * 32, "title":"热门第二篇", "publish_date":target_date, "content_type":"pdf", "source_payload":{}})
    second = store.upsert_report({"source":"qyj", "source_report_id":"B" * 32, "title":"热门第一篇", "publish_date":target_date, "content_type":"pdf", "source_payload":{}})
    outside = store.upsert_report({"source":"qyj", "source_report_id":"C" * 32, "title":"未归属文章", "publish_date":target_date, "content_type":"pdf", "source_payload":{}})
    store.record_snapshot(first.id, target_date, "HOT", 2, "a" * 64)
    store.record_snapshot(second.id, target_date, "HOT", 1, "b" * 64)
    store.record_snapshot(first.id, target_date, "STRATEGY", 1, "c" * 64)
    for report in (first, second, outside):
        store.save_analysis(report.id, "m" * 63 + str(report.id), "profile", "agnes", {"research_type":"MARKET", "one_line_summary":report.title, "evidence":[{"chunk_id":"chunk-1", "chunk_sha256":"h" * 64}]})

    hot = store.list_digest_channel_members(target_date, "HOT")
    strategy = store.list_digest_channel_members(target_date, "STRATEGY")

    assert [(member.report.id, member.snapshot.platform_order) for member in hot] == [(second.id, 1), (first.id, 2)]
    assert [(member.report.id, member.snapshot.platform_order) for member in strategy] == [(first.id, 1)]
    assert all(member.report.id != outside.id for member in hot + strategy)
