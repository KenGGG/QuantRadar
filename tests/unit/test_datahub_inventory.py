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


def test_gap_plan_uses_published_supplemental_coverage_before_queueing_work():
    from quantradar.datahub.inventory import build_gap_plan

    plan = build_gap_plan(
        {"trade_status": {"state": "PARTIAL", "coverage": {"first_date": "1990-01-01", "latest_date": "2023-06-09"}}},
        supplemental_domains={"trade_status": {"state": "VALID", "coverage": {"first_date": "2023-06-10", "latest_date": "2026-08-31"}}},
        start="2020-01-01", end="2026-08-31", requirements={"trade_status": "base-bao-daily-v1"},
    )

    assert plan["satisfied_by_base"] == []
    assert plan["satisfied_by_release"] == ["trade_status"]
    assert plan["strategy_gap"] == []


def test_coverage_contract_counts_only_expected_keys_and_compresses_missing_intervals():
    from quantradar.datahub.coverage import CoverageService

    report = CoverageService("trade-status-v1").audit(
        expected=[
            {"symbol": "000001.SZ", "trade_date": "2024-01-02", "fields": ("tradestatus", "is_st")},
            {"symbol": "000001.SZ", "trade_date": "2024-01-03", "fields": ("tradestatus", "is_st")},
            {"symbol": "000001.SZ", "trade_date": "2024-01-04", "fields": ("tradestatus", "is_st")},
        ],
        actual=[
            {"symbol": "000001.SZ", "trade_date": "2024-01-02", "tradestatus": "1", "is_st": "0"},
            {"symbol": "000001.SZ", "trade_date": "2024-01-03", "tradestatus": "1", "is_st": None},
        ],
    )

    assert report["expected_key_contract"] == "trade-status-v1"
    assert report["expected_fields"] == 6
    assert report["valid_fields"] == 3
    assert report["missing"] == [
        {"symbol": "000001.SZ", "field": "is_st", "start": "2024-01-03", "end": "2024-01-04", "expected_key_contract": "trade-status-v1"},
        {"symbol": "000001.SZ", "field": "tradestatus", "start": "2024-01-04", "end": "2024-01-04", "expected_key_contract": "trade-status-v1"},
    ]


def test_coverage_contract_keeps_non_applicable_keys_out_of_the_denominator():
    from quantradar.datahub.coverage import CoverageService

    report = CoverageService("trade-status-v1").audit(
        expected=[
            {"symbol": "000001.SZ", "trade_date": "2024-01-02", "fields": ("tradestatus",), "applicable": False},
            {"symbol": "000001.SZ", "trade_date": "2024-01-03", "fields": ("tradestatus",)},
        ],
        actual=[{"symbol": "000001.SZ", "trade_date": "2024-01-03", "tradestatus": "1"}],
    )

    assert report["expected_fields"] == 1
    assert report["valid_fields"] == 1
    assert report["missing"] == []


def test_coverage_reaudit_marks_a_work_order_satisfied_only_when_no_fields_remain():
    from quantradar.datahub.coverage import CoverageService

    outcome = CoverageService("trade-status-v1").reaudit_work_order(
        {"domain": "trade_status", "expected_key_contract": "trade-status-v1"},
        expected=[{"symbol": "600000.SH", "trade_date": "2024-01-02", "fields": ("is_st",)}],
        actual=[{"symbol": "600000.SH", "trade_date": "2024-01-02", "is_st": 0}],
    )

    assert outcome["status"] == "SATISFIED"
    assert outcome["evidence"]["remaining_gap_fingerprint"]


def test_coverage_partition_report_aggregates_field_counts_without_requiring_a_global_cartesian_product():
    from quantradar.datahub.coverage import CoverageService

    report = CoverageService("trade-status-v1").audit_partitions([
        (
            [{"symbol": "600000.SH", "trade_date": "2024-01-02", "fields": ("tradestatus", "is_st")}],
            [{"symbol": "600000.SH", "trade_date": "2024-01-02", "tradestatus": 1, "is_st": 0}],
        ),
        (
            [{"symbol": "000001.SZ", "trade_date": "2024-01-03", "fields": ("tradestatus", "is_st")}],
            [{"symbol": "000001.SZ", "trade_date": "2024-01-03", "tradestatus": 1}],
        ),
    ])

    assert report["expected_fields"] == 4
    assert report["valid_fields"] == 3
    assert report["missing_fields"] == 1
    assert report["coverage_ratio"] == 0.75
    assert report["missing"] == [{
        "symbol": "000001.SZ", "field": "is_st", "start": "2024-01-03", "end": "2024-01-03",
        "expected_key_contract": "trade-status-v1",
    }]


def test_market_status_report_separates_unsupported_and_unknown_lifecycle_from_coverage_denominator():
    from quantradar.datahub.service import build_market_trade_status_coverage_report

    report = build_market_trade_status_coverage_report(
        records=[
            {"symbol": "600000.SH", "list_date": "2024-01-02", "delist_date": None,
             "capabilities": {"trade_status": "SUPPORTED"}},
            {"symbol": "000001.SZ", "list_date": None, "capabilities": {"trade_status": "SUPPORTED"}},
            {"symbol": "430001.BJ", "list_date": "2024-01-02", "capabilities": {"trade_status": "UNSUPPORTED"}},
        ],
        calendar=["2024-01-02", "2024-01-03"], start="2024-01-02", end="2024-01-03",
        observations_by_symbol={"600000.SH": [
            {"symbol": "600000.SH", "trade_date": "2024-01-02", "tradestatus": 1, "is_st": 0},
            {"symbol": "600000.SH", "trade_date": "2024-01-03", "tradestatus": 1, "is_st": 0},
        ]},
    )

    assert report["symbols"]["supported"] == 2
    assert report["symbols"]["lifecycle_unknown"] == ["000001.SZ"]
    assert report["symbols"]["unsupported"] == ["430001.BJ"]
    assert report["expected_fields"] == 4
    assert report["valid_fields"] == 4
    assert report["coverage_ratio"] == 1.0


def test_market_status_report_cli_accepts_bounded_partition_size():
    from quantradar.datahub.cli import _parser

    args = _parser().parse_args([
        "market-trade-status-report", "--start", "2024-01-02", "--end", "2024-01-03", "--partition-size", "50",
    ])

    assert args.partition_size == 50


def test_monthly_status_dependencies_use_previous_trade_day_and_exact_constituents():
    from quantradar.datahub.inventory import monthly_status_dependencies

    dependencies = monthly_status_dependencies(
        ["2023-06-29", "2023-06-30", "2023-07-03", "2023-07-04", "2023-08-01"],
        start="2023-07-01", end="2023-08-01",
        constituents_for=lambda day: ["600000.SH"] if day == "2023-06-30" else ["000001.SZ", "600000.SH"],
    )

    assert dependencies == [
        {"rebalance_date": "2023-07-03", "status_date": "2023-06-30", "symbols": ["600000.SH"],
         "boundary_check": {"before": "2023-06-29", "after": "2023-07-03"}},
        {"rebalance_date": "2023-08-01", "status_date": "2023-07-04", "symbols": ["000001.SZ", "600000.SH"],
         "boundary_check": {"before": "2023-07-03", "after": "2023-08-01"}},
    ]


def test_service_persists_strategy_gap_plan(tmp_path, monkeypatch):
    from quantradar.config import DataHubConfig
    from quantradar.datahub.service import DataHubService

    service = DataHubService(DataHubConfig(supplemental_repo=str(tmp_path)))
    monkeypatch.setattr(service, "supplemental_inventory", lambda release_id=None: {})
    monkeypatch.setattr(service, "base_inventory", lambda release_id=None: {
        "release_id": "R1", "base_commit": "base", "domains": {
            "price": {"state": "VALID", "coverage": {"first_date": "2010-01-01", "latest_date": "2026-09-11"}},
            "trade_status": {"state": "PARTIAL", "coverage": {"first_date": "2010-01-01", "latest_date": "2023-06-09"}},
        }})

    plan = service.strategy_gap_plan("2020-01-01", "2026-08-31")
    assert plan["release_id"] == "R1"
    assert plan["strategy_gap"][0]["domain"] == "trade_status"
    assert plan["work_orders"][0]["status"] == "ENQUEUED"
    assert plan["queue_status"]["strategy"]["PENDING"] == 1
    assert (tmp_path / "gap_plan.json").is_file()


def test_market_status_plan_excludes_bse_and_keys_tasks_by_contract(tmp_path, monkeypatch):
    import json
    from quantradar.config import DataHubConfig
    from quantradar.datahub.service import DataHubService

    root = tmp_path / "supp"
    (root / "security-master").mkdir(parents=True)
    (root / "security-master" / "sh_sz.json").write_text(json.dumps({"records": [
        {"symbol": "600000.SH", "capabilities": {"trade_status": "SUPPORTED"}},
        {"symbol": "430001.BJ", "capabilities": {"trade_status": "UNSUPPORTED"}},
    ]}))
    service = DataHubService(DataHubConfig(supplemental_repo=str(root)))
    monkeypatch.setattr(service.releases, "resolve", lambda release_id=None: {"release_id": "R1", "base_commit": "base"})

    plan = service.market_trade_status_plan("2024-01-02", "2024-01-03")

    assert plan["symbol_count"] == 1
    assert plan["tasks"][0]["symbols"] == ["600000.SH"]
    assert plan["tasks"][0]["expected_key_contract"] == "baostock-trade-status-v1"


def test_market_status_plan_enqueue_preserves_each_symbol_task(tmp_path, monkeypatch):
    from quantradar.config import DataHubConfig
    from quantradar.datahub.service import DataHubService

    service = DataHubService(DataHubConfig(supplemental_repo=str(tmp_path)))
    monkeypatch.setattr(service, "market_trade_status_plan", lambda *_: {"tasks": [{
        "source_contract_id": "baostock-daily-v2", "domain": "trade_status", "fields": ["is_st"],
        "symbols": ["600000.SH"], "range": {"start": "2024-01-02", "end": "2024-01-02"},
        "gap_reason": "test", "gap_fingerprint": "a" * 64, "expected_key_contract": "baostock-trade-status-v1",
    }]})

    result = service.enqueue_market_trade_status_plan("2024-01-02", "2024-01-02")

    assert result["enqueued"] == 1
    assert result["queue_status"]["historical"]["PENDING"] == 1


def test_market_status_plan_can_enqueue_current_correction_work(tmp_path, monkeypatch):
    from quantradar.config import DataHubConfig
    from quantradar.datahub.service import DataHubService

    service = DataHubService(DataHubConfig(supplemental_repo=str(tmp_path)))
    monkeypatch.setattr(service, "market_trade_status_plan", lambda *_: {"tasks": [{
        "source_contract_id": "baostock-daily-v2", "domain": "trade_status", "fields": ["is_st"],
        "symbols": ["600000.SH"], "range": {"start": "2024-01-02", "end": "2024-01-02"},
        "gap_reason": "test", "gap_fingerprint": "b" * 64, "expected_key_contract": "baostock-trade-status-v1",
    }]})

    result = service.enqueue_market_trade_status_plan("2024-01-02", "2024-01-02", queue_name="current")

    assert result["enqueued"] == 1
    assert result["queue_status"]["current"]["PENDING"] == 1


def test_current_rolling_window_supersedes_only_overlapping_pending_task(tmp_path):
    from quantradar.datahub.work_queue import DataHubWorkQueue

    queue = DataHubWorkQueue(tmp_path / "work-queue.json")
    first = {"source_contract_id": "baostock-daily-v2", "domain": "trade_status", "fields": ["is_st"],
             "symbols": ["600000.SH"], "range": {"start": "2024-01-02", "end": "2024-01-31"},
             "gap_reason": "current", "gap_fingerprint": "first", "expected_key_contract": "contract"}
    second = {**first, "range": {"start": "2024-01-03", "end": "2024-02-01"}, "gap_fingerprint": "second"}
    old = queue.enqueue("current", first)["task"]
    queue.enqueue("current", second)

    rows = {row["task_id"]: row for row in queue.status()["tasks"]}
    assert rows[old["task_id"]]["status"] == "OBSOLETE"
    assert queue.status()["counts"]["current"]["PENDING"] == 1


def test_work_queue_enqueues_many_tasks_in_one_durable_operation(tmp_path):
    from quantradar.datahub.work_queue import DataHubWorkQueue

    queue = DataHubWorkQueue(tmp_path / "work-queue.json")
    tasks = [{"source_contract_id": "baostock-daily-v2", "domain": "trade_status", "fields": ["is_st"],
              "symbols": [symbol], "range": {"start": "2024-01-02", "end": "2024-01-02"},
              "gap_reason": "test", "gap_fingerprint": symbol * 8} for symbol in ("a", "b")]

    outcomes = queue.enqueue_many("historical", tasks)

    assert [item["status"] for item in outcomes] == ["ENQUEUED", "ENQUEUED"]
    assert queue.status()["counts"]["historical"]["PENDING"] == 2


def test_market_status_worker_keeps_only_rows_in_a_reaudited_gap():
    from quantradar.datahub.service import remaining_trade_status_rows

    rows = [
        {"symbol": "600000.SH", "trade_date": "2024-01-02"},
        {"symbol": "600000.SH", "trade_date": "2024-01-03"},
        {"symbol": "600000.SH", "trade_date": "2024-01-04"},
    ]
    selected = remaining_trade_status_rows(rows, [{"symbol": "600000.SH", "field": "is_st", "start": "2024-01-03", "end": "2024-01-03"}])

    assert selected == [{"symbol": "600000.SH", "trade_date": "2024-01-03"}]


def test_release_status_merge_keeps_non_null_base_values_without_hiding_patch_fields():
    from quantradar.datahub.service import merge_trade_status_observations

    merged = merge_trade_status_observations(
        [{"symbol": "600000.SH", "trade_date": "2024-01-03", "tradestatus": 1, "is_st": None}],
        [{"symbol": "600000.SH", "trade_date": "2024-01-03", "tradestatus": 0, "is_st": 0}],
    )

    assert merged == [{"symbol": "600000.SH", "trade_date": "2024-01-03", "tradestatus": 1, "is_st": 0}]


def test_market_status_execution_binds_to_current_release_but_keeps_planned_release():
    from quantradar.datahub.service import execution_release_task

    task = execution_release_task({"release_id": "R-plan", "task_id": "task"}, "R-current")

    assert task["release_id"] == "R-current"
    assert task["planned_release_id"] == "R-plan"


def test_work_queue_claim_matching_does_not_consume_another_domain(tmp_path):
    from quantradar.datahub.work_queue import DataHubWorkQueue

    queue = DataHubWorkQueue(tmp_path / "work-queue.json")
    for domain in ("trade_status", "valuation_daily"):
        queue.enqueue("historical", {"source_contract_id": "source", "domain": domain, "fields": [],
                                      "symbols": [domain], "range": {"start": "2024-01-02", "end": "2024-01-02"},
                                      "gap_reason": "test", "gap_fingerprint": domain})

    claimed = queue.claim_matching("historical", domain="trade_status", limit=5)

    assert [task["domain"] for task in claimed] == ["trade_status"]
    assert queue.status()["counts"]["historical"]["PENDING"] == 1


def test_work_queue_defer_can_rebase_a_follow_up_audit_to_its_published_release(tmp_path):
    from quantradar.datahub.work_queue import DataHubWorkQueue

    queue = DataHubWorkQueue(tmp_path / "work-queue.json")
    task = queue.enqueue("historical", {"source_contract_id": "source", "domain": "trade_status", "fields": [],
                                         "symbols": ["600000.SH"], "range": {"start": "2024-01-02", "end": "2024-01-02"},
                                         "gap_reason": "test", "gap_fingerprint": "gap", "release_id": "R1"})["task"]
    queue.claim_matching("historical", domain="trade_status", limit=1)

    deferred = queue.defer(task["task_id"], evidence={"published_release_id": "R2"}, release_id="R2")

    assert deferred["task"]["status"] == "PENDING"
    assert deferred["task"]["release_id"] == "R2"


def test_work_queue_recovers_abandoned_running_domain_work(tmp_path):
    from quantradar.datahub.work_queue import DataHubWorkQueue

    queue = DataHubWorkQueue(tmp_path / "work-queue.json")
    task = queue.enqueue("historical", {"source_contract_id": "source", "domain": "trade_status", "fields": [],
                                         "symbols": ["600000.SH"], "range": {"start": "2024-01-02", "end": "2024-01-02"},
                                         "gap_reason": "test", "gap_fingerprint": "recover"})["task"]
    queue.claim_matching("historical", domain="trade_status", limit=1)

    assert queue.recover_running("historical", domain="trade_status", evidence={"recovery": "test"}) == 1
    assert queue.status()["tasks"][0]["task_id"] == task["task_id"]
    assert queue.status()["counts"]["historical"]["PENDING"] == 1


def test_low_beta_status_plan_has_exact_symbols_and_release_fingerprint(tmp_path, monkeypatch):
    from quantradar.config import DataHubConfig
    from quantradar.datahub.service import DataHubService

    service = DataHubService(DataHubConfig(supplemental_repo=str(tmp_path), release_root=str(tmp_path / "releases")))
    monkeypatch.setattr(service.releases, "resolve", lambda release_id=None: {"release_id": "R1", "base_commit": "base"})
    monkeypatch.setattr(service, "_low_beta_status_dependencies", lambda start, end, base_commit: [
        {"rebalance_date": "2023-09-01", "status_date": "2023-08-31", "symbols": ["000001.SZ", "600519.SH"],
         "boundary_check": {"before": "2023-08-30", "after": "2023-09-01"}},
    ])

    plan = service.low_beta_status_plan("2023-09-01", "2023-09-01")
    task = plan["tasks"][0]
    assert plan["release_id"] == "R1"
    assert task["source_contract_id"] == "baostock-daily-v2"
    assert task["range"] == {"start": "2023-08-31", "end": "2023-08-31"}
    assert task["symbols"] == ["000001.SZ", "600519.SH"]
    assert len(task["gap_fingerprint"]) == 64


def test_low_beta_status_collection_archives_raw_and_stages_only_requested_keys(tmp_path, monkeypatch):
    import hashlib
    from quantradar.config import DataHubConfig
    from quantradar.datahub.adapters import FetchedRows
    from quantradar.datahub.service import DataHubService

    service = DataHubService(DataHubConfig(supplemental_repo=str(tmp_path / "supp"), release_root=str(tmp_path / "releases"),
                                           raw_root=str(tmp_path / "raw"), journal_root=str(tmp_path / "journals")))
    monkeypatch.setattr(service, "low_beta_status_plan", lambda *_args, **_kwargs: {
        "release_id": "R1", "base_commit": "base", "tasks": [{"symbols": ["600519.SH"], "range": {"start": "2023-08-31", "end": "2023-08-31"}}],
        "plan_fingerprint": "a" * 64, "key_count": 1, "symbol_count": 1,
    })
    row = {"trade_date": "2023-08-31", "symbol": "600519.SH", "tradestatus": 1, "is_st": 0, "turn": 0.1,
           "source": "baostock", "raw_sha256": hashlib.sha256(b"raw").hexdigest(), "adapter_version": "test", "fetched_at": "now",
           "available_date": None, "pit_status": "PARTIAL", "source_contract_id": "baostock-daily-v2"}
    class Adapter:
        def __init__(self, **_kwargs): pass
        def daily_bundles(self, symbols, *_args):
            assert symbols == ["600519.SH"]
            yield "600519.SH", FetchedRows("trade_status_daily", b"raw", [row], "baostock", "now")
    monkeypatch.setattr("quantradar.datahub.service.BaostockAdapter", Adapter)

    result = service.collect_low_beta_status("2023-09-01", "2023-09-01")
    assert result["completed"] == 1
    assert result["staged_rows"] == 1
    assert (tmp_path / "supp" / "staging" / "low-beta-status" / "600519.SH.jsonl").is_file()
    assert service.raw.read(__import__("hashlib").sha256(b"raw").hexdigest()) == b"raw"


def test_low_beta_status_plan_fingerprint_changes_with_required_dates(tmp_path, monkeypatch):
    from quantradar.config import DataHubConfig
    from quantradar.datahub.service import DataHubService

    service = DataHubService(DataHubConfig(supplemental_repo=str(tmp_path), release_root=str(tmp_path / "releases")))
    monkeypatch.setattr(service.releases, "resolve", lambda release_id=None: {"release_id": "R1", "base_commit": "base"})
    monkeypatch.setattr(service, "_low_beta_status_dependencies", lambda start, end, base_commit: [
        {"rebalance_date": end, "status_date": start, "symbols": ["600519.SH"], "boundary_check": {"before": None, "after": end}},
    ])
    first = service.low_beta_status_plan("2023-08-31", "2023-09-01")
    second = service.low_beta_status_plan("2023-09-01", "2023-09-02")
    assert first["plan_fingerprint"] != second["plan_fingerprint"]


def test_low_beta_status_journal_reuses_completed_scope_after_release_changes(tmp_path, monkeypatch):
    import json
    from quantradar.config import DataHubConfig
    from quantradar.datahub.service import DataHubService

    service = DataHubService(DataHubConfig(supplemental_repo=str(tmp_path), release_root=str(tmp_path / "releases"), journal_root=str(tmp_path / "journals")))
    monkeypatch.setattr(service, "_low_beta_status_dependencies", lambda *_args: [
        {"rebalance_date": "2023-09-01", "status_date": "2023-08-31", "symbols": ["600519.SH"],
         "boundary_check": {"before": "2023-08-30", "after": "2023-09-01"}},
    ])
    monkeypatch.setattr(service.releases, "resolve", lambda release_id=None: {"release_id": release_id or "R2", "base_commit": "base"})
    old = service.low_beta_status_plan("2023-09-01", "2023-09-01", "R1")
    old_path = tmp_path / "journals" / f"low-beta-status-{old['plan_fingerprint'][:16]}.json"
    old_path.parent.mkdir(parents=True)
    old_path.write_text(json.dumps({"units": {"600519.SH": {"status": "COMPLETE", "raw_sha256": "a" * 64}}, "operation_id": "low-beta-status-repair"}))

    new = service.low_beta_status_plan("2023-09-01", "2023-09-01", "R2")
    journal = service._low_beta_status_journal(new)

    assert old["plan_fingerprint"] != new["plan_fingerprint"]
    assert journal.data["units"]["600519.SH"]["status"] == "COMPLETE"
    assert journal.data["migrated_from"] == old_path.name


def test_low_beta_missing_status_is_not_covered_only_after_base_price_ends():
    from quantradar.datahub.service import low_beta_status_coverage_outcome

    assert low_beta_status_coverage_outcome(["2025-03-31"], "2025-02-05") == "NOT_COVERED"
    assert low_beta_status_coverage_outcome(["2025-03-31"], "2025-04-01") == "UNRESOLVED"


def test_trade_status_candidates_are_grouped_by_day_for_partition_reads():
    from quantradar.datahub.service import group_trade_status_candidates_by_day

    grouped = group_trade_status_candidates_by_day([
        {"trade_date": "2023-08-31T00:00:00", "symbol": "600519.SH"},
        {"trade_date": "2023-08-31", "symbol": "000001.SZ"},
        {"trade_date": "2023-09-01", "symbol": "600519.SH"},
    ])

    assert grouped == {
        "2023-08-31": {"SH600519": "600519.SH", "SZ000001": "000001.SZ"},
        "2023-09-01": {"SH600519": "600519.SH"},
    }


def test_work_queue_is_idempotent_and_rotates_all_three_queues(tmp_path):
    from quantradar.datahub.work_queue import DataHubWorkQueue

    queue = DataHubWorkQueue(tmp_path / "work-queue.json")
    def task(name):
        return {"source_contract_id": "contract", "domain": name, "range": {"start": "2023-09-01", "end": "2023-09-01"},
                "gap_reason": "test", "gap_fingerprint": name}
    assert queue.enqueue("current", task("current"))["status"] == "ENQUEUED"
    assert queue.enqueue("strategy", task("strategy"))["status"] == "ENQUEUED"
    assert queue.enqueue("historical", task("historical"))["status"] == "ENQUEUED"
    assert queue.enqueue("current", task("current"))["status"] == "NO_CHANGE"
    assert [queue.claim_next()["queue"] for _ in range(3)] == ["current", "strategy", "historical"]


def test_work_queue_records_a_reaudit_satisfied_or_obsolete_outcome(tmp_path):
    from quantradar.datahub.work_queue import DataHubWorkQueue

    queue = DataHubWorkQueue(tmp_path / "work-queue.json")
    task = queue.enqueue("strategy", {
        "source_contract_id": "baostock-daily-v2", "domain": "trade_status", "fields": ["is_st"],
        "symbols": ["600000.SH"], "range": {"start": "2024-01-02", "end": "2024-01-02"},
        "gap_reason": "test", "gap_fingerprint": "a" * 64,
    })["task"]
    queue.claim_next()

    satisfied = queue.finish(task["task_id"], "SATISFIED", evidence={"remaining_gap_fingerprint": "b" * 64})

    assert satisfied["status"] == "SATISFIED"
    assert queue.status()["counts"]["strategy"]["SATISFIED"] == 1


def test_work_queue_blocks_a_pending_task_superseded_by_a_new_source_contract(tmp_path):
    from quantradar.datahub.work_queue import DataHubWorkQueue

    queue = DataHubWorkQueue(tmp_path / "work-queue.json")
    base = {"domain": "trade_status", "range": {"start": "2023-09-01", "end": "2023-09-01"}, "gap_reason": "test", "gap_fingerprint": "same"}
    old = queue.enqueue("strategy", {**base, "source_contract_id": "old"})["task"]
    new = queue.enqueue("strategy", {**base, "source_contract_id": "new"})["task"]
    tasks = {task["task_id"]: task for task in queue.status()["tasks"]}
    assert tasks[old["task_id"]]["status"] == "BLOCKED"
    assert tasks[old["task_id"]]["superseded_by"] == new["task_id"]


def test_work_queue_persists_terminal_evidence_and_never_reopens_it(tmp_path):
    from quantradar.datahub.work_queue import DataHubWorkQueue

    queue = DataHubWorkQueue(tmp_path / "work-queue.json")
    task = queue.enqueue("historical", {"source_contract_id": "contract", "domain": "trade_status",
                                         "range": {"start": "2023-09-01", "end": "2023-09-01"},
                                         "gap_reason": "test", "gap_fingerprint": "one"})["task"]
    assert queue.claim_next()["task_id"] == task["task_id"]
    finished = queue.finish(task["task_id"], "QUARANTINED", evidence={"reason": "source conflict"})
    assert finished["task"]["evidence"] == {"reason": "source conflict"}
    assert queue.finish(task["task_id"], "COMPLETE")["status"] == "NO_CHANGE"


def test_baostock_bundle_keeps_status_and_never_maps_ncf_to_ocf():
    from quantradar.datahub.sources import normalize_baostock_daily_bundle

    rows = normalize_baostock_daily_bundle([{
        "date": "2023-09-01", "code": "sh.600519", "open": "1852.83", "high": "1865.47", "low": "1846.03", "close": "1851.05",
        "volume": "13145.19", "amount": "2438622.738", "turn": "0.12", "tradestatus": "1", "isST": "0",
        "peTTM": "33.7", "pbMRQ": "11.5", "psTTM": "16.7", "pcfNcfTTM": "2142.3",
    }], raw_sha256="a" * 64, fetched_at="2026-09-11T00:00:00Z", adapter_version="test")

    assert rows["price"][0]["close"] == 1851.05
    assert {key: rows["trade_status"][0][key] for key in ("trade_date", "symbol", "tradestatus", "is_st", "turn")} == {"trade_date": "2023-09-01", "symbol": "600519.SH", "tradestatus": 1, "is_st": 0, "turn": 0.12}
    assert rows["trade_status"][0]["raw_sha256"] == "a" * 64
    assert rows["trade_status"][0]["source_contract_id"] == "baostock-daily-v2"
    assert rows["valuation"][0]["pcf_ncf_ttm"] == 2142.3
    assert "pcf_ocf_ttm" not in rows["valuation"][0]


def test_baostock_daily_bundles_emit_auditable_status_rows(monkeypatch):
    from contextlib import contextmanager
    from quantradar.datahub.adapters import BaostockAdapter

    class Result:
        error_code = "0"
        error_msg = ""
        fields = ["date", "code", "open", "high", "low", "close", "volume", "amount", "turn", "tradestatus", "isST"]
        def __init__(self): self.used = False
        def next(self):
            if self.used: return False
            self.used = True
            return True
        def get_row_data(self): return ["2023-08-31", "sh.600519", "1", "1", "1", "1", "100", "1000", "0.1", "1", "0"]

    class Client:
        def query_history_k_data_plus(self, *_args, **_kwargs): return Result()

    adapter = BaostockAdapter()
    @contextmanager
    def fake_session():
        yield Client()
    monkeypatch.setattr(adapter, "_session", fake_session)
    symbol, fetched = next(adapter.daily_bundles(["600519.SH"], "2023-08-31", "2023-08-31"))
    assert symbol == "600519.SH"
    assert fetched.dataset == "trade_status_daily"
    assert fetched.rows[0]["source_contract_id"] == "baostock-daily-v2"
    assert fetched.rows[0]["symbol"] == "600519.SH"


def test_baostock_pe_pb_ps_candidate_does_not_require_or_create_ocf(tmp_path):
    import hashlib
    import json
    from quantradar.datahub.quality import validate_shard

    row = {"symbol": "600519.SH", "trade_date": "2023-09-01", "source": "baostock", "pit_status": "PARTIAL",
           "adapter_version": "test", "raw_sha256": "a" * 64, "pe_ttm": 33.7, "pb_mrq": 11.5, "ps_ttm": 16.7,
           "pcf_ncf_ttm": 2142.3}
    content = (json.dumps(row) + "\n").encode()
    path = tmp_path / "600519.SH.jsonl"
    path.write_bytes(content)
    result = validate_shard(path, "600519.SH", {"row_count": 1, "staged_result_sha256": hashlib.sha256(content).hexdigest(), "source_contract_id": "baostock-daily-v2"})
    assert result["status"] == "PASS"
    assert result["source_contract_ids"] == ["baostock-daily-v2"]


def test_status_patch_only_fills_missing_base_values():
    import pandas as pd
    from quantradar.providers.investment_data.provider import overlay_status_patch

    base = pd.DataFrame({"is_st": [0.0, float("nan")], "tradestatus": [1.0, float("nan")]}, index=pd.to_datetime(["2023-06-09", "2023-06-12"]))
    patched = overlay_status_patch(base, [{"trade_date": "2023-06-09", "is_st": 1, "tradestatus": 0}, {"trade_date": "2023-06-12", "is_st": 0, "tradestatus": 1}])

    assert patched.loc["2023-06-09", "is_st"] == 0
    assert patched.loc["2023-06-12", "is_st"] == 0
    assert patched.loc["2023-06-12", "tradestatus"] == 1


def test_status_patch_adds_dates_absent_from_base_table():
    import pandas as pd
    from quantradar.providers.investment_data.provider import overlay_status_patch

    patched = overlay_status_patch(pd.DataFrame({"is_st": pd.Series(dtype="float64"), "tradestatus": pd.Series(dtype="float64")}), [{"trade_date": "2023-09-01", "is_st": 0, "tradestatus": 1}])
    assert patched.loc["2023-09-01", "is_st"] == 0


def test_price_patch_adds_only_dates_absent_from_base_table():
    import pandas as pd
    from quantradar.providers.investment_data.provider import overlay_price_patch

    base = pd.DataFrame({"open": [10.0], "close": [11.0]}, index=pd.to_datetime(["2023-06-09"]))
    rows = [
        {"trade_date": "2023-06-09", "open": 1, "close": 2, "volume": 3, "amount": 4},
        {"trade_date": "2023-06-12", "open": 3, "close": 4, "volume": 5, "amount": 6},
    ]
    patched = overlay_price_patch(base, rows)
    assert patched.loc["2023-06-09", "close"] == 11
    assert patched.loc["2023-06-12", "close"] == 4


def test_bao_raw_price_fills_absent_final_row_but_never_replaces_final_row():
    import pandas as pd
    from quantradar.providers.investment_data.provider import overlay_bao_raw_price
    final = pd.DataFrame({"open": [10.0, float("nan")], "close": [11.0, float("nan")]}, index=pd.to_datetime(["2023-06-09", "2023-06-12"]))
    bao = pd.DataFrame({"open": [1.0, 2.0], "close": [2.0, 3.0]}, index=pd.to_datetime(["2023-06-09", "2023-06-12"]))
    resolved = overlay_bao_raw_price(final, bao)
    assert resolved.loc["2023-06-09", "close"] == 11
    assert resolved.loc["2023-06-12", "close"] == 3


def test_provider_reads_release_pinned_raw_price_patch_when_base_has_no_date():
    import pandas as pd
    from types import SimpleNamespace
    from quantradar.providers.investment_data.provider import InvestmentDataProvider

    provider = object.__new__(InvestmentDataProvider)
    provider._data_usage = {"price_calls": 0, "price_symbols": set(), "status_calls": 0, "status_patch_rows": 0, "price_patch_rows": 0, "valuation_calls": 0, "industry_calls": 0}
    provider._price_units = "joinquant-shares-yuan-v2"
    provider._release_scope = SimpleNamespace(release_id="R-price", manifest={"datasets": {"a_stock_eod_price": {"row_count": 1}}})
    provider._fetch_raw_price = lambda *_args, **_kwargs: pd.DataFrame({"open": pd.Series(dtype="float64"), "close": pd.Series(dtype="float64")})
    class Reader:
        def prices(self, symbols, start, end):
            assert symbols == ["600519.SH"] and start == "2020-08-19" and end == "2020-08-19"
            return {"600519.SH": [{"trade_date": "2020-08-19", "symbol": "600519.SH", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100, "amount": 1050}]}
    provider._supplemental_reader = Reader()
    result = provider.get_price("600519.XSHG", start_date="2020-08-19", end_date="2020-08-19", fields=["open", "close"])
    assert result.loc["2020-08-19", "close"] == 10.5
    assert list(result.columns) == ["open", "close"]
    assert provider.data_usage()["supplemental_price_rows"] == 1


def test_paused_keeps_unknown_when_trade_status_is_missing():
    import pandas as pd
    from quantradar.providers.investment_data.provider import InvestmentDataProvider

    provider = object.__new__(InvestmentDataProvider)
    provider._supplemental_reader = None
    provider._release_scope = None
    provider._fetch_table_cols = lambda *args, **kwargs: pd.DataFrame(
        {"tradestatus": [1.0, 0.0, float("nan")]}, index=pd.to_datetime(["2023-09-01", "2023-09-04", "2023-09-05"])
    )
    result = provider._paused_from_trade_status("SH600519", "2023-09-01", "2023-09-05", None, pd.to_datetime(["2023-09-01", "2023-09-04", "2023-09-05"]))
    assert bool(result.iloc[0]) is False
    assert bool(result.iloc[1]) is True
    assert pd.isna(result.iloc[2])


def test_one_day_status_request_uses_the_asof_date_not_an_older_observation():
    import pandas as pd
    from quantradar.providers.investment_data.provider import InvestmentDataProvider

    provider = object.__new__(InvestmentDataProvider)
    provider._data_usage = {"status_calls": 0, "status_patch_rows": 0}
    provider._extras_cache = {}
    provider._supplemental_reader = None
    provider._release_scope = None
    seen = {}
    def fetch(_table, _fields, _symbols, start, end, count, **_kwargs):
        seen.update(start=start, end=end, count=count)
        return {"SH600519": pd.DataFrame({"is_st": [], "tradestatus": []})}
    provider._fetch_table_cols_many = fetch
    result = provider.get_extras("is_st", ["600519.XSHG"], end_date="2024-01-02", count=1)
    assert seen == {"start": "2024-01-02", "end": "2024-01-02", "count": 1}
    assert result.empty


def test_provider_usage_keeps_base_and_supplemental_contributions_separate():
    from quantradar.providers.investment_data.provider import InvestmentDataProvider

    provider = object.__new__(InvestmentDataProvider)
    provider._data_usage = {"price_calls": 2, "price_symbols": {"SH600519", "SZ000001"}, "status_calls": 1,
                            "status_patch_rows": 3, "valuation_calls": 4, "industry_calls": 5}
    assert provider.data_usage() == {"base_final_price_calls": 2, "base_final_price_symbols": 2,
                                     "trade_status_calls": 1, "supplemental_trade_status_rows": 3, "supplemental_price_rows": 0,
                                     "supplemental_valuation_calls": 4, "supplemental_industry_calls": 5}


def test_get_extras_cache_isolated_by_release():
    import pandas as pd
    from types import SimpleNamespace
    from quantradar.providers.investment_data.provider import InvestmentDataProvider

    provider = object.__new__(InvestmentDataProvider)
    provider._data_usage = {"status_calls": 0, "status_patch_rows": 0}
    provider._extras_cache = {}
    provider._release_scope = SimpleNamespace(
        release_id="R1", manifest={"datasets": {"trade_status_daily": {}}}
    )
    provider._supplemental_reader = None
    calls = []

    def fetch(_table, _fields, symbols, _start, _end, _count, **_kwargs):
        calls.append(tuple(symbols))
        return {symbol: pd.DataFrame({"is_st": [0], "tradestatus": [1]}, index=pd.to_datetime(["2023-09-01"])) for symbol in symbols}

    provider._fetch_table_cols_many = fetch
    provider.get_extras("is_st", ["600519.XSHG"], end_date="2023-09-01", count=1)
    provider._release_scope = SimpleNamespace(
        release_id="R2", manifest={"datasets": {"trade_status_daily": {}}}
    )
    provider.get_extras("is_st", ["600519.XSHG"], end_date="2023-09-01", count=1)
    assert calls == [("SH600519",), ("SH600519",)]


def test_status_patch_validation_rejects_duplicate_or_invalid_state():
    from quantradar.datahub.publication import status_patch_delta, validate_trade_status_base_gap, validate_trade_status_patch

    good = [{"trade_date": "2023-09-01", "symbol": "600519.SH", "tradestatus": 1, "is_st": 0, "turn": 0.12,
             "source": "baostock", "raw_sha256": "a" * 64, "adapter_version": "test", "source_contract_id": "baostock-daily-v2", "fetched_at": "2026-09-11T00:00:00Z", "available_date": None, "pit_status": "PARTIAL"}]
    assert validate_trade_status_patch(good)["status"] == "PASS"
    assert validate_trade_status_patch(good + good)["status"] == "FAIL"
    bad = [dict(good[0], tradestatus=3)]
    assert validate_trade_status_patch(bad)["status"] == "FAIL"
    assert validate_trade_status_base_gap(good, set())["status"] == "PASS"
    overlap = validate_trade_status_base_gap(good, {("2023-09-01", "600519.SH")})
    assert overlap == {"status": "FAIL", "base_overlap_count": 1, "base_overlaps": [("2023-09-01", "600519.SH")]}
    existing = {("2023-09-01", "600519.SH"): dict(good[0])}
    assert status_patch_delta(good, existing) == {"new_rows": [], "conflicts": []}
    legacy_existing = {("2023-09-01", "600519.SH"): {key: value for key, value in good[0].items() if key != "source_contract_id"}}
    assert status_patch_delta(good, legacy_existing) == {"new_rows": [], "conflicts": []}
    assert status_patch_delta([dict(good[0], raw_sha256="b" * 64)], existing) == {"new_rows": [], "conflicts": []}
    assert status_patch_delta([dict(good[0], is_st=1)], existing)["conflicts"] == [("2023-09-01", "600519.SH")]
    assert status_patch_delta([dict(good[0], source_contract_id="another-qualified-contract")], existing)["conflicts"] == [("2023-09-01", "600519.SH")]
