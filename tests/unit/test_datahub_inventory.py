from __future__ import annotations


def test_inventory_distinguishes_final_and_reusable_source_tables():
    from quantradar.datahub.inventory import classify_base_tables

    report = classify_base_tables(
        {
            "final_a_stock_eod_price": ["tradedate", "symbol", "open", "high", "low", "close", "volume", "amount"],
            "ts_a_stock_eod_price": ["tradedate", "symbol", "open", "high", "low", "close", "volume", "amount"],
            "bao_a_stock_eod_info": ["tradedate", "symbol", "tradestatus", "is_st", "turn"],
            "ts_a_stock_list": ["ts_code", "list_date", "delist_date"],
        },
        {
            "final_a_stock_eod_price": {"first_date": "2010-01-01", "latest_date": "2026-09-11", "stocks": 2, "row_count": 4},
            "ts_a_stock_eod_price": {"first_date": "2010-01-01", "latest_date": "2020-01-01", "stocks": 2, "row_count": 2},
            "bao_a_stock_eod_info": {"first_date": "2010-01-01", "latest_date": "2023-06-09", "stocks": 2, "row_count": 3},
            "ts_a_stock_list": {"first_date": "1990-01-01", "latest_date": "2022-07-15", "stocks": 2, "row_count": 2},
        },
    )

    assert report["price"]["selected_table"] == "final_a_stock_eod_price"
    assert report["price"]["reusable_tables"] == ["ts_a_stock_eod_price"]
    assert report["price"]["units"] == {"volume": "hand", "amount": "thousand_yuan"}
    assert report["trade_status"]["state"] == "PARTIAL"
    assert report["lifecycle"]["state"] == "PARTIAL"


def test_inventory_does_not_treat_missing_source_table_as_a_gap():
    from quantradar.datahub.inventory import classify_base_tables

    report = classify_base_tables(
        {"final_a_stock_eod_price": ["tradedate", "symbol", "open", "high", "low", "close", "volume", "amount"]},
        {"final_a_stock_eod_price": {"first_date": "2020-01-01", "latest_date": "2020-01-02", "stocks": 1, "row_count": 2}},
    )

    assert report["price"]["state"] == "VALID"
    assert report["price"]["reusable_tables"] == []
    assert report["trade_status"]["state"] == "UNKNOWN"


def test_scan_base_discovers_schema_and_uses_actual_date_columns():
    from quantradar.datahub.inventory import scan_base

    class Cursor:
        def __init__(self): self.last = ""
        def execute(self, sql): self.last = sql
        def fetchall(self):
            if "information_schema" in self.last: return [{"name": "final_a_stock_eod_price"}]
            if "SHOW COLUMNS" in self.last: return [{"Field": field} for field in ("tradedate", "symbol", "open", "high", "low", "close", "volume", "amount")]
            return []
        def fetchone(self): return {"first_date": "2020-01-01", "latest_date": "2020-01-02", "stocks": 1, "row_count": 2}

    report = scan_base(Cursor())
    assert report["domains"]["price"]["coverage"]["latest_date"] == "2020-01-02"


def test_service_persists_inventory_at_the_release_base_commit(tmp_path, monkeypatch):
    from quantradar.config import DataHubConfig
    from quantradar.datahub.service import DataHubService

    config = DataHubConfig(supplemental_repo=str(tmp_path))
    service = DataHubService(config)
    monkeypatch.setattr(service.releases, "resolve", lambda release_id=None: {"release_id": "R1", "base_commit": "base-commit"})
    monkeypatch.setattr("quantradar.datahub.inventory.scan_base", lambda cursor: {"tables": {}, "domains": {"price": {"state": "VALID"}}})

    seen = {}
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): return False
    class Connection:
        def cursor(self): return Cursor()
        def close(self): pass
    def connect(**kwargs):
        seen.update(kwargs)
        return Connection()
    monkeypatch.setattr("quantradar.datahub.service.pymysql.connect", connect)

    report = service.base_inventory()
    assert seen["database"] == "investment_data/base-commit"
    assert report["release_id"] == "R1"
    assert (tmp_path / "base_inventory.json").is_file()


def test_index_alias_requires_equal_constituents_on_every_overlap():
    from quantradar.datahub.inventory import validate_index_alias

    valid = validate_index_alias("000300.SH", "399300.SZ", [
        ("2020-01-02", {"000001.SZ", "600000.SH"}, {"000001.SZ", "600000.SH"}),
        ("2020-01-31", {"000001.SZ", "600000.SH"}, {"000001.SZ", "600000.SH"}),
    ])
    assert valid["state"] == "VALID"
    assert valid["effective_from"] == "2020-01-02"
    assert valid["effective_to"] == "2020-01-31"

    mismatch = validate_index_alias("000300.SH", "399300.SZ", [
        ("2020-01-02", {"000001.SZ"}, {"600000.SH"}),
    ])
    assert mismatch["state"] == "CONFLICT"


def test_gap_plan_uses_base_coverage_before_scheduling_network_work():
    from quantradar.datahub.inventory import build_gap_plan

    plan = build_gap_plan(
        {"price": {"state": "VALID", "coverage": {"first_date": "1990-01-01", "latest_date": "2026-09-11"}},
         "trade_status": {"state": "PARTIAL", "coverage": {"first_date": "1990-01-01", "latest_date": "2023-06-09"}}},
        start="2020-01-01", end="2026-08-31", requirements={"price": "base-final-price-v1", "trade_status": "base-bao-daily-v1"},
    )

    assert plan["strategy_gap"] == [{"domain": "trade_status", "range": {"start": "2023-06-10", "end": "2026-08-31"}, "state": "UNKNOWN", "source_contract_id": "base-bao-daily-v1"}]
    assert plan["satisfied_by_base"] == ["price"]


def test_service_persists_strategy_gap_plan(tmp_path, monkeypatch):
    from quantradar.config import DataHubConfig
    from quantradar.datahub.service import DataHubService

    service = DataHubService(DataHubConfig(supplemental_repo=str(tmp_path)))
    monkeypatch.setattr(service, "base_inventory", lambda release_id=None: {
        "release_id": "R1", "base_commit": "base", "domains": {
            "price": {"state": "VALID", "coverage": {"first_date": "2010-01-01", "latest_date": "2026-09-11"}},
            "trade_status": {"state": "PARTIAL", "coverage": {"first_date": "2010-01-01", "latest_date": "2023-06-09"}},
        }})

    plan = service.strategy_gap_plan("2020-01-01", "2026-08-31")
    assert plan["release_id"] == "R1"
    assert plan["strategy_gap"][0]["domain"] == "trade_status"
    assert (tmp_path / "gap_plan.json").is_file()
