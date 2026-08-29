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


def test_analysis_is_idempotent_for_same_markdown_and_prompt(store) -> None:
    report = store.upsert_report(_report_payload())
    payload = {"summary": "结论", "research_type": "MARKET"}

    first = store.save_analysis(report.id, "md-hash", "prompt-v1", "agnes-2.5-flash", payload)
    second = store.save_analysis(report.id, "md-hash", "prompt-v1", "agnes-2.5-flash", payload)

    assert first.id == second.id
    assert store.analysis_count() == 1


def test_analysis_profile_change_creates_a_new_version(store) -> None:
    report = store.upsert_report(_report_payload())
    payload = {"summary": "结论", "research_type": "MARKET"}

    first = store.save_analysis(report.id, "md-hash", "profile-a", "agnes-2.5-flash", payload)
    second = store.save_analysis(report.id, "md-hash", "profile-b", "agnes-2.6", payload)

    assert first.id != second.id
    assert store.analysis_count() == 2


def test_analysis_keeps_raw_markdown_hash_separate_from_profile_hash(store) -> None:
    report = store.upsert_report(_report_payload())
    row = store.save_analysis(report.id, "a" * 64, "profile-a", "agnes-2.5-flash", {"summary": "结论", "research_type": "MARKET"})

    assert row.markdown_sha256 == "a" * 64
    assert row.analysis_profile_hash == "profile-a"


def test_analysis_chunks_are_saved_with_report_and_markdown_scope(store) -> None:
    from quantradar.research.llm.chunking import plan_chunks
    report = store.upsert_report(_report_payload())

    store.save_analysis_chunks(report.id, "m" * 64, plan_chunks("# 标题\n正文", 100))
    rows = store.list_analysis_chunks(report.id, "m" * 64)

    assert [(row.chunk_index, row.source_start, row.source_end, row.chunk_sha256) for row in rows] == [(1, 0, 7, rows[0].chunk_sha256)]


def test_saved_analysis_has_deterministic_result_hash(store) -> None:
    report = store.upsert_report(_report_payload())
    row = store.save_analysis(report.id, "m" * 64, "profile", "model", {"research_type": "MARKET", "summary": "结论"})

    assert row.analysis_hash
    assert len(row.analysis_hash) == 64
    assert row.agnes_version == "agnes-http-v1"
    assert row.schema_version == "schema-v1"
    assert row.chunking_version == "chunking-v1"


def test_create_schema_upgrades_existing_analysis_table_without_dropping_rows(tmp_path) -> None:
    from sqlalchemy import create_engine, inspect, text
    from quantradar.research.config import ResearchSettings
    from quantradar.research.storage import ResearchStore
    url = f"sqlite+pysqlite:///{tmp_path / 'legacy.db'}"
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE research_reports (id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE research_analyses (id INTEGER PRIMARY KEY, report_id INTEGER NOT NULL, analysis_type VARCHAR(32) NOT NULL, model VARCHAR(128) NOT NULL, prompt_version VARCHAR(64) NOT NULL, input_hash VARCHAR(64) NOT NULL, output_json JSON NOT NULL, created_at DATETIME)"))
        conn.execute(text("INSERT INTO research_analyses VALUES (1, 1, 'MARKET', 'old', 'v1', 'oldhash', '{}', NULL)"))
    store = ResearchStore(ResearchSettings(url, tmp_path / "data", tmp_path / "profile"))
    store.create_schema()
    columns = {column["name"] for column in inspect(store.engine).get_columns("research_analyses")}
    assert {"markdown_sha256", "analysis_profile_hash", "status"} <= columns
