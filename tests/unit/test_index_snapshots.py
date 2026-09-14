from __future__ import annotations


def test_normalize_csi_weight_keeps_percent_raw_and_fraction():
    from quantradar.datahub.index_snapshots import normalize_csi_weights
    rows = normalize_csi_weights([{"成分券代码": "600000", "权重": 0.524, "成分券名称": "浦发", "交易所": "上海证券交易所"}])
    assert rows == [{"security_code": "600000.SH", "weight_raw": 0.524, "weight_unit": "PERCENT", "weight_fraction": 0.00524}]


def test_normalize_sw_component_keeps_weight_unit_unknown_and_member_date():
    from quantradar.datahub.index_snapshots import normalize_sw_components
    rows = normalize_sw_components([{"证券代码": "000001", "证券名称": "平安", "最新权重": 3.57, "计入日期": "2025-12-15"}])
    assert rows[0]["security_code"] == "000001.SZ"
    assert rows[0]["weight_raw"] == 3.57
    assert rows[0]["member_effective_date"] == "2025-12-15"
    assert rows[0]["member_effective_semantics"] == "SOURCE_MEMBER_INCLUSION_DATE"


def test_index_snapshot_candidate_requires_members_and_declared_time_semantics():
    from quantradar.datahub.index_snapshots import validate_index_snapshot_candidate
    candidate = {"dataset_type":"CSI_CONSTITUENTS","index_code":"000300.SH","source_date":"2026-09-14","observed_at":"2026-09-14T20:30:00+08:00","raw_sha256":"a"*64,"content_hash":"b"*64,"source":"akshare","adapter_version":"x","effective_semantics":"SOURCE_DATE_NOT_EFFECTIVE","qualification":"RAW_EVIDENCE_ONLY","pit_status":"PARTIAL"}
    assert validate_index_snapshot_candidate(candidate, [{"security_code":"600000.SH"}])["status"] == "PASS"
    assert validate_index_snapshot_candidate(candidate, [])["status"] == "FAIL"
