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
    assert "dataset_type, index_code, source_date, source, revision_no" in schema
    assert "CREATE TABLE IF NOT EXISTS qr_index_constituent_snapshot" in schema
    assert "CREATE TABLE IF NOT EXISTS qr_index_weight_snapshot" in schema
    assert "CREATE TABLE IF NOT EXISTS qr_sw_index_component_snapshot" in schema


def test_snapshot_writer_does_not_rewrite_identical_business_content():
    from quantradar.datahub.dolt import SupplementalStore

    executed = []
    class Cursor:
        def execute(self, sql, args=()): executed.append((sql, args))
        def fetchone(self): return {"snapshot_id": "old", "content_hash": "same", "revision_no": 1}
        def __enter__(self): return self
        def __exit__(self, *_): return False
    class Connection:
        def cursor(self): return Cursor()
        def commit(self): executed.append(("COMMIT", ()))
    result = SupplementalStore(Connection()).write_index_snapshot(
        version={"dataset_type": "CSI_CONSTITUENTS", "index_code": "000300.SH", "source_date": "2026-09-14", "observed_at": "2026-09-14T20:30:00+08:00", "content_hash": "same", "raw_sha256": "a" * 64, "source": "akshare", "adapter_version": "x", "effective_semantics": "UNKNOWN", "qualification": "RAW_EVIDENCE_ONLY", "pit_status": "PARTIAL"},
        constituents=[{"security_code": "600000.SH"}], weights=[], sw_components=[],
    )
    assert result["action"] == "NO_CHANGE"
    assert not any("INSERT INTO qr_index_snapshot_version" in sql for sql, _ in executed)


def test_snapshot_revision_chain_is_scoped_to_its_source():
    from quantradar.datahub.dolt import SupplementalStore
    executed = []
    class Cursor:
        def execute(self, sql, args=()): executed.append((sql, args))
        def fetchone(self): return None
        def __enter__(self): return self
        def __exit__(self, *_): return False
    class Connection:
        def cursor(self): return Cursor()
        def commit(self): pass
    SupplementalStore(Connection()).write_index_snapshot(
        version={"dataset_type": "CSI_CONSTITUENTS", "index_code": "000300.SH", "source_date": "2026-09-14", "observed_at": "2026-09-14T20:30:00+08:00", "content_hash": "same", "raw_sha256": "a" * 64, "source": "official", "adapter_version": "x", "effective_semantics": "UNKNOWN", "qualification": "RAW_EVIDENCE_ONLY", "pit_status": "PARTIAL"},
        constituents=[], weights=[], sw_components=[],
    )
    lookup = executed[0]
    assert "source=%s" in lookup[0]
    assert lookup[1][-1] == "official"


def test_schema_upgrade_rekeys_existing_snapshot_revision_index_by_source():
    from quantradar.datahub.dolt import SupplementalStore
    executed = []
    class Cursor:
        last = ""
        def execute(self, sql, args=()): self.last = sql; executed.append(sql)
        def fetchall(self):
            if "SHOW COLUMNS" in self.last:
                return [{"Field": "source_contract_id"}]
            if "SHOW INDEX" in self.last:
                return [
                    {"Column_name": "dataset_type", "Seq_in_index": 1},
                    {"Column_name": "index_code", "Seq_in_index": 2},
                    {"Column_name": "source_date", "Seq_in_index": 3},
                    {"Column_name": "revision_no", "Seq_in_index": 4},
                ]
            return []
        def __enter__(self): return self
        def __exit__(self, *_): return False
    class Connection:
        def cursor(self): return Cursor()
        def commit(self): pass
    SupplementalStore(Connection()).ensure_schema()
    assert any("DROP INDEX qr_index_snapshot_revision" in sql for sql in executed)
    assert any("source_date, source, revision_no" in sql for sql in executed)


def test_explicit_snapshot_reader_keeps_unknown_source_date_out_of_as_of_reads(monkeypatch):
    from quantradar.datahub.reader import SupplementalReader
    reader = SupplementalReader(lambda: None)
    monkeypatch.setattr(reader, "_query", lambda sql, args: [{"snapshot_id": "s", "source_date": None, "observed_at": "2026-09-14T20:30:00+08:00", "pit_status": "PARTIAL"}])

    assert reader.get_index_snapshot("000300.SH", as_of="2026-09-01") is None


def test_observed_before_date_includes_all_observations_on_that_local_date():
    from quantradar.datahub.v3_contracts import snapshot_eligibility
    result = snapshot_eligibility({"source_date": "2026-09-14", "observed_at": "2026-09-14T20:30:00+08:00", "pit_status": "PARTIAL"}, observed_before="2026-09-14")
    assert result["eligible"] is True


def test_reader_expands_date_only_observed_before_to_end_of_day(monkeypatch):
    from quantradar.datahub.reader import SupplementalReader
    reader = SupplementalReader(lambda: None)
    seen = []
    def query(sql, args):
        seen.append(args)
        return []
    monkeypatch.setattr(reader, "_query", query)
    reader.get_index_snapshot("000300.SH", observed_before="2026-09-14")
    assert seen[0][-1] == "2026-09-14T23:59:59.999999+08:00"
