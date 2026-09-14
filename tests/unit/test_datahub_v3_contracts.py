from __future__ import annotations

import pytest


def test_snapshot_content_hash_ignores_observation_metadata_and_row_order():
    from quantradar.datahub.v3_contracts import snapshot_content_hash

    first = [
        {"security_code": "600000.SH", "weight_raw": 0.5, "weight_unit": "PERCENT", "observed_at": "2026-09-14T20:30:00+08:00", "raw_sha256": "a" * 64},
        {"security_code": "000001.SZ", "weight_raw": 1.25, "weight_unit": "PERCENT", "fetched_at": "2026-09-14T20:30:02+08:00"},
    ]
    reordered = [
        {"security_code": "000001.SZ", "weight_raw": 1.25, "weight_unit": "PERCENT", "observed_at": "2026-09-15T20:30:00+08:00", "raw_sha256": "b" * 64},
        {"security_code": "600000.SH", "weight_raw": 0.5, "weight_unit": "PERCENT"},
    ]
    changed = [dict(first[0]), {"security_code": "000001.SZ", "weight_raw": 1.26, "weight_unit": "PERCENT"}]

    assert snapshot_content_hash(first) == snapshot_content_hash(reordered)
    assert snapshot_content_hash(first) != snapshot_content_hash(changed)


def test_snapshot_query_refuses_unknown_source_date_for_as_of_and_strict_pit():
    from quantradar.datahub.v3_contracts import snapshot_eligibility

    unknown = {"source_date": None, "observed_at": "2026-09-14T20:30:00+08:00", "pit_status": "PARTIAL"}
    assert snapshot_eligibility(unknown, observed_before="2026-09-20") == {"eligible": True, "reason": "SOURCE_DATE_UNKNOWN"}
    assert snapshot_eligibility(unknown, as_of="2026-09-01") == {"eligible": False, "reason": "SOURCE_DATE_UNKNOWN"}
    assert snapshot_eligibility(unknown, observed_before="2026-09-20", strict_pit=True) == {"eligible": False, "reason": "SOURCE_DATE_UNKNOWN"}


def test_statement_mapping_identity_keeps_supplier_version_separate_from_mapping_version():
    from quantradar.datahub.v3_contracts import statement_mapping_identity

    assert statement_mapping_identity("statement-A", "v1") == ("statement-A", "v1")
    assert statement_mapping_identity("statement-A", "v2") == ("statement-A", "v2")
    with pytest.raises(ValueError, match="statement_version_id"):
        statement_mapping_identity("", "v1")


def test_g0_audit_records_raw_evidence_without_claiming_strict_pit(tmp_path):
    from quantradar.datahub.store import RawStore
    from quantradar.datahub.v3_audit import record_probe

    result = record_probe(
        RawStore(tmp_path),
        dataset="financial_balance_sheet",
        source="akshare:stock_balance_sheet_by_report_em",
        request={"symbol": "SH600519"},
        rows=[{"REPORT_DATE": "2025-12-31", "NOTICE_DATE": "2026-03-30", "TOTAL_ASSETS": 1}],
        observed_at="2026-09-14T20:30:00+08:00",
        adapter_version="akshare-test",
    )

    assert result["raw_sha256"]
    assert result["qualification"] == "RAW_EVIDENCE_ONLY"
    assert result["pit_status"] == "PARTIAL"
    assert result["schema"]["columns"] == ["NOTICE_DATE", "REPORT_DATE", "TOTAL_ASSETS"]


def test_source_audit_runner_records_success_and_failure_per_probe(tmp_path):
    from quantradar.datahub.store import RawStore
    from quantradar.datahub.v3_audit import run_probes

    result = run_probes(
        RawStore(tmp_path),
        [
            ("one", "adapter", {"code": "A"}, lambda: [{"x": 1}]),
            ("two", "adapter", {"code": "B"}, lambda: (_ for _ in ()).throw(TimeoutError("slow"))),
        ],
        observed_at="2026-09-14T20:30:00+08:00",
        adapter_version="test",
    )

    assert result["status"] == "PARTIAL"
    assert result["receipts"][0]["request"] == {"code": "A"}
    assert result["failures"] == [{"dataset": "two", "request": {"code": "B"}, "error_type": "TimeoutError", "error": "slow"}]


def test_snapshot_revision_plan_appends_only_when_business_content_changes():
    from quantradar.datahub.v3_contracts import snapshot_revision_plan

    existing = {"snapshot_id": "old", "content_hash": "same", "revision_no": 1}
    assert snapshot_revision_plan(existing, "same") == {"action": "NO_CHANGE", "revision_no": 1, "supersedes_snapshot_id": None}
    assert snapshot_revision_plan(existing, "changed") == {"action": "APPEND", "revision_no": 2, "supersedes_snapshot_id": "old"}
    assert snapshot_revision_plan(None, "first") == {"action": "APPEND", "revision_no": 1, "supersedes_snapshot_id": None}


def test_supplemental_schema_has_immutable_snapshot_version_and_member_tables():
    from quantradar.datahub.dolt import _SCHEMA

    schema = "\n".join(_SCHEMA)
    assert "CREATE TABLE IF NOT EXISTS qr_index_snapshot_version" in schema
    assert "UNIQUE KEY qr_index_snapshot_revision" in schema
    assert "CREATE TABLE IF NOT EXISTS qr_index_constituent_snapshot" in schema
    assert "CREATE TABLE IF NOT EXISTS qr_index_weight_snapshot" in schema
    assert "CREATE TABLE IF NOT EXISTS qr_sw_index_component_snapshot" in schema
