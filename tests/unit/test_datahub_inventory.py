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


def test_low_beta_missing_status_is_not_covered_only_after_base_price_ends():
    from quantradar.datahub.service import low_beta_status_coverage_outcome

    assert low_beta_status_coverage_outcome(["2025-03-31"], "2025-02-05") == "NOT_COVERED"
    assert low_beta_status_coverage_outcome(["2025-03-31"], "2025-04-01") == "UNRESOLVED"


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
                                     "trade_status_calls": 1, "supplemental_trade_status_rows": 3,
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
