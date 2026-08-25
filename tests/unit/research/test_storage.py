from datetime import date
from pathlib import Path

import pytest


@pytest.fixture
def store(tmp_path: Path):
    from quantradar.research.config import ResearchSettings
    from quantradar.research.storage import ResearchStore

    settings = ResearchSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'research.db'}",
        data_dir=tmp_path / "research-data",
        qyj_profile_dir=tmp_path / "qyj-profile",
    )
    result = ResearchStore(settings)
    result.create_schema()
    return result


def _report_payload(title: str = "测试报告") -> dict:
    return {
        "source": "qyj",
        "source_report_id": "A" * 32,
        "title": title,
        "publish_date": date(2026, 8, 24),
        "content_type": "pdf",
        "source_payload": {"id": "A" * 32},
    }


def test_report_unique_by_source_and_source_report_id(store) -> None:
    """Changing a title must update the same upstream report, not duplicate it."""
    first = store.upsert_report(_report_payload())
    second = store.upsert_report(_report_payload("更新后的标题"))

    assert first.id == second.id
    assert store.report_count() == 1
    assert second.title == "更新后的标题"


def test_snapshot_keeps_same_report_in_multiple_channels(store) -> None:
    """One report in HOT and STRATEGY must remain visible in both channels."""
    report = store.upsert_report(_report_payload())
    store.record_snapshot(report.id, date(2026, 8, 24), "HOT", 1, "hash-hot")
    store.record_snapshot(report.id, date(2026, 8, 24), "STRATEGY", 3, "hash-strategy")

    snapshots = store.list_snapshots(date(2026, 8, 24))
    assert [(row.channel, row.platform_order) for row in snapshots] == [("HOT", 1), ("STRATEGY", 3)]


def test_stage_success_is_idempotent(store) -> None:
    """A successful identical input must be skipped on a rerun."""
    report = store.upsert_report(_report_payload())

    first = store.begin_stage(report.id, "DOWNLOAD", "input-hash")
    store.finish_stage(first.id, "SUCCESS", output_hash="output-hash")
    second = store.begin_stage(report.id, "DOWNLOAD", "input-hash")

    assert second.status == "SUCCESS"
    assert second.id == first.id
    assert second.attempt == 1


def test_outbox_notification_key_is_unique(store) -> None:
    """The normal delivery path may reserve a digest only once."""
    first = store.reserve_outbox("research-digest:2026-08-24:abc", date(2026, 8, 24), "abc", "payload")
    second = store.reserve_outbox("research-digest:2026-08-24:abc", date(2026, 8, 24), "abc", "payload")

    assert first.id == second.id
    assert store.outbox_count() == 1
