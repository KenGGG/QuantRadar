from __future__ import annotations


def test_financial_schema_physically_separates_raw_versions_from_mappings():
    from quantradar.datahub.dolt import _SCHEMA
    schema = "\n".join(_SCHEMA)
    assert "CREATE TABLE IF NOT EXISTS qr_stock_statement_version" in schema
    assert "CREATE TABLE IF NOT EXISTS qr_stock_balance_sheet" in schema
    assert "PRIMARY KEY (statement_version_id, mapping_version)" in schema
    assert "conservative_available_at" in schema
    assert "availability_rule_version" in schema


def test_date_only_announcement_uses_next_fixed_trading_session():
    from quantradar.datahub.financial_canonical import conservative_available_at
    assert conservative_available_at("2026-03-30", "DATE_ONLY", ["2026-03-30", "2026-03-31"]) == ("2026-03-31T09:30:00+08:00", "CN_DATE_ONLY_NEXT_TRADING_SESSION_V1")


def test_map_income_row_preserves_nullable_fields_and_canonical_values():
    from quantradar.datahub.financial_canonical import map_statement_row
    result = map_statement_row("income", {"TOTAL_OPERATE_INCOME": 10, "OPERATE_PROFIT": 3, "TOTAL_PROFIT": 4, "NETPROFIT": 2, "PARENT_NETPROFIT": 1})
    assert result["operating_revenue"] == 10.0
    assert result["net_profit_parent"] == 1.0


def test_statement_version_identity_is_content_specific():
    from quantradar.datahub.financial_canonical import statement_version_id
    a = statement_version_id("600519.SH", "income", "2025-12-31", "a" * 64)
    b = statement_version_id("600519.SH", "income", "2025-12-31", "b" * 64)
    assert a != b
    assert a == statement_version_id("600519.SH", "income", "2025-12-31", "a" * 64)


def test_financial_writer_does_not_repeat_fixed_mapping_columns():
    from quantradar.datahub.dolt import SupplementalStore
    sql=[]
    class C:
        def execute(self, query, args=()): sql.append(query)
        def __enter__(self): return self
        def __exit__(self,*_): return False
    class Conn:
        def cursor(self): return C()
        def commit(self): pass
    v={"statement_version_id":"s","symbol":"600519.SH","statement_type":"income","report_period":"2025-12-31","statement_scope":"UNKNOWN","period_type":"YTD","announcement_precision":"DATE_ONLY","source_fetch_at":"x","source":"x","raw_sha256":"a"*64,"adapter_version":"x","pit_status":"PARTIAL","qualification":"x","raw_payload_json":"{}"}
    SupplementalStore(Conn()).write_financial_statement(v,{"mapping_version":"v1","conservative_available_at":None,"availability_rule_version":None,"net_profit":1})
    assert sql[-1].count("availability_rule_version") == 1
