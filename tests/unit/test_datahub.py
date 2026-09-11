from __future__ import annotations

import json
from unittest.mock import patch

import pytest


def test_datahub_overview_release_excludes_per_symbol_audit_metadata():
    from quantradar.api.app import _overview_release

    summary = _overview_release({
        "release_id": "R1", "base_commit": "base", "supplemental_commit": "supp",
        "published_at": "2026-09-11T00:00:00Z", "datasets": {"valuation_daily": {"row_count": 2}},
        "source_adapters": {"valuation": ["eastmoney"]},
        "metadata": {"quality": "PASS", "pit": "PARTIAL", "isolated": {"000001.SZ": "SYMBOL_DATA_ERROR"},
                     "shard_hashes": {"000001.SZ": "a" * 64}},
    })

    assert summary == {
        "release_id": "R1", "base_commit": "base", "supplemental_commit": "supp",
        "published_at": "2026-09-11T00:00:00Z", "datasets": {"valuation_daily": {"row_count": 2}},
        "source_adapters": {"valuation": ["eastmoney"]},
        "metadata": {"quality": "PASS", "pit": "PARTIAL"},
    }


def test_datahub_overview_sources_describe_base_and_supplemental_status_separately():
    from quantradar.api.app import _overview_data_sources

    rows = _overview_data_sources(
        {"datasets": {"trade_status_daily": {"stocks": 2, "row_count": 3, "source": ["baostock"]}}},
        {"datasets": {"行情": {"stocks": 4}, "ST / 停牌": {"stocks": 3, "latest_date": "2023-06-09"}}},
    )

    status_rows = [row for row in rows if row["domain"] == "trade_status"]
    assert [(row["storage"], row["read_rule"]) for row in status_rows] == [
        ("/data/investment_data", "优先读取"),
        ("/data/quantradar_data", "仅补基础库缺失记录"),
    ]
    assert status_rows[1]["coverage"]["row_count"] == 3


def test_request_governor_persists_one_retry_and_opens_circuit_across_restart(tmp_path):
    from quantradar.datahub.governor import CircuitOpen, RequestGovernor

    calls = []
    governor = RequestGovernor(tmp_path, "eastmoney", interval_seconds=0, cooldown_seconds=600, failure_threshold=2)

    def disconnected_once():
        calls.append("attempt")
        if len(calls) == 1:
            raise ConnectionError("RemoteDisconnected")
        return "ok"

    assert governor.call("valuation_daily/2016-01-04", disconnected_once) == "ok"
    ledger = governor.status()
    assert ledger["logical_requests"] == 1
    assert ledger["actual_http_attempts"] == 2
    assert ledger["retry"] == 1
    assert ledger["success"] == 1
    assert ledger["RemoteDisconnected"] == 1

    with pytest.raises(ConnectionError):
        governor.call("valuation_daily/2016-01-05", lambda: (_ for _ in ()).throw(ConnectionError("timeout")))
    with pytest.raises(ConnectionError):
        governor.call("valuation_daily/2016-01-06", lambda: (_ for _ in ()).throw(ConnectionError("timeout")))

    restarted = RequestGovernor(tmp_path, "eastmoney", interval_seconds=0, cooldown_seconds=600, failure_threshold=2)
    with pytest.raises(CircuitOpen):
        restarted.call("valuation_daily/2016-01-07", lambda: "must not run")
    assert restarted.status()["circuit_open"] is True


def test_request_governor_opens_immediately_for_rate_limit_without_retry(tmp_path):
    from quantradar.datahub.governor import CircuitOpen, RequestGovernor

    governor = RequestGovernor(tmp_path, "eastmoney", interval_seconds=0, cooldown_seconds=600)
    calls = []

    def limited():
        calls.append(1)
        raise RuntimeError("HTTP 429")

    with pytest.raises(RuntimeError, match="429"):
        governor.call("valuation_daily/2016-01-04", limited)
    assert calls == [1]
    assert governor.status()["429"] == 1
    assert governor.status()["retry"] == 0
    with pytest.raises(CircuitOpen):
        governor.call("valuation_daily/2016-01-05", lambda: "must not run")


def test_request_governor_can_disable_outer_retry_for_an_sdk_owned_retry_policy(tmp_path):
    from quantradar.datahub.governor import RequestGovernor

    governor = RequestGovernor(tmp_path, "eastmoney", interval_seconds=0)
    calls = []
    with pytest.raises(ConnectionError):
        governor.call("valuation_daily/600519", lambda: (calls.append(1), (_ for _ in ()).throw(ConnectionError("timeout")))[1], max_attempts=1)
    assert calls == [1]
    assert governor.status()["actual_http_attempts"] == 1
    assert governor.status()["retry"] == 0


def test_request_governor_records_sdk_invocation_without_claiming_opaque_http_attempts(tmp_path):
    from quantradar.datahub.governor import RequestGovernor

    governor = RequestGovernor(tmp_path, "eastmoney", interval_seconds=0)
    assert governor.call("valuation_daily/600519", lambda: "ok", max_attempts=1, http_attempts_known=False) == "ok"
    assert governor.status()["sdk_invocations"] == 1
    assert governor.status()["actual_http_attempts"] == 0
    observed = governor.observed_status()
    assert observed["sdk_attempts_opaque"] == 1
    assert observed["observed_http_attempts"] == 0
    assert observed["observed_403"] == 0


def test_canonical_security_master_adds_only_delta_records():
    from quantradar.datahub.service import canonical_sh_sz_security_master

    base = [{"symbol": "600000.SH", "list_date": "1999-11-10", "source": "investment_data"}]
    lifecycle = [
        {"symbol": "600000.SH", "list_date": "1999-11-10", "source": "baostock"},
        {"symbol": "688999.SH", "list_date": "2023-01-03", "source": "baostock"},
        {"symbol": "430001.BJ", "list_date": "2023-01-03", "source": "baostock"},
    ]

    master = canonical_sh_sz_security_master(base, lifecycle)

    assert [row["symbol"] for row in master] == ["600000.SH", "688999.SH"]
    assert master[0]["source"] == "investment_data"
    assert master[1]["source"] == "baostock"


def test_journal_creates_pending_entries_without_overwriting_completed(tmp_path):
    from quantradar.datahub.store import UpdateJournal

    journal = UpdateJournal(tmp_path / "journal.json")
    journal.complete("600000.SH", raw_sha256="a" * 64, row_count=1)
    assert journal.ensure_pending(["600000.SH", "688999.SH"], reason="security master delta") == 1
    assert journal.data["units"]["600000.SH"]["status"] == "COMPLETE"
    assert journal.data["units"]["688999.SH"]["status"] == "PENDING"


def test_valuation_health_probe_selects_only_three_failed_symbols(tmp_path):
    from quantradar.config import DataHubConfig
    from quantradar.datahub.service import DataHubService
    from quantradar.datahub.store import UpdateJournal

    service = DataHubService(DataHubConfig(journal_root=str(tmp_path)))
    journal = UpdateJournal(tmp_path / "valuation_daily-mvp.json")
    for symbol in ("000003.SZ", "000001.SZ", "000002.SZ", "600000.SH"):
        journal.fail(symbol, "parse")

    assert service.valuation_health_probe_symbols() == ["000001.SZ", "000002.SZ", "000003.SZ"]


def test_shard_runner_defers_the_remaining_shards_when_governor_circuit_opens(tmp_path):
    from quantradar.datahub.governor import CircuitOpen
    from quantradar.datahub.mvp import ShardRunner
    from quantradar.datahub.store import UpdateJournal

    calls = []
    def fetch(symbol):
        calls.append(symbol)
        if symbol == "b":
            raise CircuitOpen("eastmoney circuit open until tomorrow")
        return [{"trade_date": "2018-01-02", "symbol": symbol}]

    journal = UpdateJournal(tmp_path / "journal.json")
    runner = ShardRunner(tmp_path / "stage", journal, fetch)
    assert runner.run(["a", "b", "c"])["completed"] == 1
    assert calls == ["a", "b"]
    assert journal.data["units"]["b"]["status"] == "PENDING"
    assert "c" not in journal.data["units"]


def test_shard_runner_honors_persisted_cooperative_pause_before_next_shard(tmp_path):
    from quantradar.datahub.mvp import ShardRunner
    from quantradar.datahub.store import UpdateJournal

    journal = UpdateJournal(tmp_path / "journal.json")
    journal.start("valuation-mvp", dataset="valuation_daily")
    journal.request_pause()
    calls: list[str] = []
    runner = ShardRunner(tmp_path / "stage", journal, lambda symbol: calls.append(symbol) or [{"trade_date": "2018-01-02", "symbol": symbol}])
    runner.run(["a", "b"])
    assert calls == []
    assert journal.data["phases"]["download"]["status"] == "PAUSED"
    assert journal.data["heartbeat"]["current_shard"] is None


def test_eastmoney_date_slice_fetches_every_page_and_preserves_pcf_ocf_precision(tmp_path):
    from quantradar.datahub.adapters import EastmoneyValuationAdapter
    from quantradar.datahub.governor import RequestGovernor

    payloads = [
        {"result": {"total": 2, "pages": 2, "data": [{
            "TRADE_DATE": "2016-01-04", "SECURITY_CODE": "600005", "SECUCODE": "600005.SH",
            "PE_TTM": "-43.879609", "PB_MRQ": "0.937746", "PS_TTM": "1.234567", "PCF_OCF_TTM": "34.814607",
        }]}},
        {"result": {"total": 2, "pages": 2, "data": [{
            "TRADE_DATE": "2016-01-04", "SECURITY_CODE": "000001", "SECUCODE": "000001.SZ",
            "PE_TTM": "8.123456", "PB_MRQ": "0.987654", "PS_TTM": "2.345678", "PCF_OCF_TTM": "4.567891",
        }]}},
    ]

    class Response:
        def __init__(self, payload): self.payload = payload
        def raise_for_status(self): pass
        def json(self): return self.payload

    class Session:
        def __init__(self): self.pages = []
        def get(self, _url, *, params, **_kwargs):
            self.pages.append(params["pageNumber"])
            return Response(payloads[len(self.pages) - 1])

    session = Session()
    adapter = EastmoneyValuationAdapter(
        governor=RequestGovernor(tmp_path, "eastmoney", interval_seconds=0), session=session, page_size=1
    )
    fetched = adapter.valuation_date("2016-01-04")

    assert session.pages == ["1", "2"]
    assert [row["symbol"] for row in fetched.rows] == ["000001.SZ", "600005.SH"]
    assert fetched.rows[1]["pcf_ocf_ttm"] == 34.814607
    assert "pcf_ncf_ttm" not in fetched.rows[0]
    assert b"34.814607" in fetched.raw_bytes


def test_eastmoney_date_slice_records_empty_response_as_schema_failure(tmp_path):
    from quantradar.datahub.adapters import EastmoneyValuationAdapter
    from quantradar.datahub.governor import RequestGovernor

    class Response:
        def raise_for_status(self): pass
        def json(self): return {"result": {"total": 0, "pages": 0, "data": []}}

    class Session:
        def get(self, *_args, **_kwargs): return Response()

    adapter = EastmoneyValuationAdapter(governor=RequestGovernor(tmp_path, "eastmoney", interval_seconds=0), session=Session())
    with pytest.raises(RuntimeError, match="schema invalid") as error:
        adapter.valuation_date("2016-01-04")
    assert b'"total":0' in error.value.raw_bytes
    assert adapter.governor.status()["schema_invalid"] == 1
    assert adapter.governor.status()["retry"] == 0


def test_eastmoney_http_rate_limit_is_recorded_by_the_governor(tmp_path):
    from quantradar.datahub.adapters import EastmoneyValuationAdapter
    from quantradar.datahub.governor import RequestGovernor

    class Response:
        def raise_for_status(self): raise RuntimeError("HTTP 429")

    class Session:
        def get(self, *_args, **_kwargs): return Response()

    governor = RequestGovernor(tmp_path, "eastmoney", interval_seconds=0)
    adapter = EastmoneyValuationAdapter(governor=governor, session=Session())
    with pytest.raises(RuntimeError, match="429"):
        adapter.valuation_date("2016-01-04")
    assert governor.status()["429"] == 1
    assert governor.status()["circuit_open"] is True


def test_valuation_normalization_preserves_negative_ratio_and_rejects_bad_number():
    from quantradar.datahub.sources import normalize_valuation_rows

    rows = normalize_valuation_rows(
        [
            {
                "date": "2016-01-04",
                "code": "sh.600005",
                "peTTM": "-43.879609",
                "pbMRQ": "0.937746",
                "psTTM": "",
                "pcfNcfTTM": "34.814607",
            }
        ],
        source="baostock",
        raw_sha256="a" * 64,
        fetched_at="2026-09-09T08:00:00+00:00",
    )
    assert rows[0]["symbol"] == "600005.SH"
    assert rows[0]["pe_ttm"] == -43.879609
    assert rows[0]["ps_ttm"] is None
    assert rows[0]["pit_status"] == "PARTIAL"

    with pytest.raises(ValueError, match="peTTM"):
        normalize_valuation_rows(
            [{"date": "2016-01-04", "code": "sh.600005", "peTTM": "not-a-number"}],
            source="baostock",
            raw_sha256="a" * 64,
            fetched_at="2026-09-09T08:00:00+00:00",
        )


def test_lifecycle_as_of_never_excludes_a_security_before_known_delisting():
    from quantradar.datahub.sources import lifecycle_active_as_of, normalize_lifecycle_row

    row = normalize_lifecycle_row(
        {
            "code": "sh.600005",
            "ipoDate": "1999-08-03",
            "outDate": "2017-02-14",
            "status": "0",
        },
        raw_sha256="b" * 64,
        fetched_at="2026-09-09T08:00:00+00:00",
    )
    assert lifecycle_active_as_of(row, "2016-01-04") is True
    assert lifecycle_active_as_of(row, "2017-02-14") is False
    assert lifecycle_active_as_of(row, "2017-02-15") is False


def test_sw_level_one_intervals_are_effective_dated_and_same_day_conflicts_fail():
    from quantradar.datahub.sources import build_sw_level_one_intervals

    intervals = build_sw_level_one_intervals(
        [
            {"code": "000001", "start_date": "1991-04-03", "industry_code": "440101"},
            {"code": "000001", "start_date": "2014-02-21", "industry_code": "480101"},
        ],
        raw_sha256="c" * 64,
        fetched_at="2026-09-09T08:00:00+00:00",
    )
    assert [(row["industry_code"], row["effective_to"]) for row in intervals] == [
        ("440000", "2014-02-20"),
        ("480000", None),
    ]

    numeric_code = build_sw_level_one_intervals(
        [{"code": 1.0, "start_date": "2016-01-04", "industry_code": 440101.0}],
        raw_sha256="c" * 64,
        fetched_at="2026-09-09T08:00:00+00:00",
    )
    assert numeric_code[0]["symbol"] == "000001.SZ"
    assert numeric_code[0]["industry_code"] == "440000"

    with pytest.raises(ValueError, match="conflicting"):
        build_sw_level_one_intervals(
            [
                {"code": "000001", "start_date": "2014-02-21", "industry_code": "480101"},
                {"code": "000001", "start_date": "2014-02-21", "industry_code": "490101"},
            ],
            raw_sha256="c" * 64,
            fetched_at="2026-09-09T08:00:00+00:00",
        )


def test_release_publication_changes_current_only_after_a_valid_manifest(tmp_path):
    from quantradar.datahub.release import ReleaseStore

    store = ReleaseStore(tmp_path)
    first = store.publish(
        base_commit="base-a",
        supplemental_commit="supp-a",
        datasets={"valuation_daily": {"version": "v1", "pit_status": "PARTIAL"}},
        source_adapters={"baostock": "0.9.3"},
    )
    assert store.current()["release_id"] == first["release_id"]
    with pytest.raises(ValueError, match="supplemental_commit"):
        store.publish(
            base_commit="base-b",
            supplemental_commit="",
            datasets={},
            source_adapters={},
        )
    assert store.current()["release_id"] == first["release_id"]
    assert json.loads((tmp_path / "current.json").read_text())["release_id"] == first["release_id"]


def test_raw_store_is_content_addressed_and_detects_corruption(tmp_path):
    from quantradar.datahub.store import RawStore

    store = RawStore(tmp_path)
    receipt = store.put("baostock/valuation/600005/2016", b"date,peTTM\n2016-01-04,-43\n")
    assert receipt["sha256"] == store.put("ignored-name", b"date,peTTM\n2016-01-04,-43\n")["sha256"]
    assert store.read(receipt["sha256"]) == b"date,peTTM\n2016-01-04,-43\n"
    (tmp_path / "raw" / receipt["sha256"]).write_bytes(b"altered")
    with pytest.raises(ValueError, match="hash mismatch"):
        store.read(receipt["sha256"])


def test_update_journal_resumes_only_completed_units(tmp_path):
    from quantradar.datahub.store import UpdateJournal

    journal = UpdateJournal(tmp_path / "journal.json")
    journal.start("backfill-1", dataset="valuation_daily")
    journal.complete("600005:2016", raw_sha256="d" * 64, row_count=270)
    journal.fail("600006:2016", "source timeout")
    reloaded = UpdateJournal(tmp_path / "journal.json")
    assert reloaded.completed_units() == {"600005:2016"}
    assert reloaded.failed_units() == {"600006:2016": "source timeout"}


def test_update_journal_tracks_explicit_gap_states_heartbeat_and_phase(tmp_path):
    from quantradar.datahub.store import UpdateJournal

    journal = UpdateJournal(tmp_path / "journal.json")
    journal.start("backfill-1", dataset="valuation_daily")
    journal.running("600519")
    journal.gap("600005", "NOT_COVERED", "delisted history unavailable")
    journal.gap("000001:2017", "LEGAL_EMPTY", "not listed")
    journal.heartbeat(phase="download", current_shard="600519", pid=42)
    journal.phase("audit", "RUNNING")
    journal.phase("audit", "DONE")

    reloaded = UpdateJournal(tmp_path / "journal.json")
    assert reloaded.data["units"]["600519"]["status"] == "RUNNING"
    assert reloaded.data["units"]["600005"]["status"] == "NOT_COVERED"
    assert reloaded.data["heartbeat"]["current_shard"] == "600519"
    assert reloaded.data["phases"]["audit"]["status"] == "DONE"


def test_update_journal_keeps_health_probe_evidence(tmp_path):
    from quantradar.datahub.store import UpdateJournal

    journal = UpdateJournal(tmp_path / "journal.json")
    journal.record_probe(symbols=["002505.SZ", "002506.SZ", "002507.SZ"], outcome="HEALTHY")
    assert UpdateJournal(tmp_path / "journal.json").data["health_probes"][-1]["outcome"] == "HEALTHY"


def test_health_probe_retries_failed_symbols_instead_of_skipping_them(tmp_path):
    from quantradar.config import DataHubConfig
    from quantradar.datahub.service import DataHubService
    from quantradar.datahub.store import UpdateJournal

    config = DataHubConfig(
        supplemental_repo=str(tmp_path / "repo"), raw_root=str(tmp_path / "raw"),
        journal_root=str(tmp_path / "journals"), release_root=str(tmp_path / "releases"),
    )
    journal = UpdateJournal(tmp_path / "journals" / "valuation_daily-mvp.json")
    for symbol in ["000022.SZ", "002504.SZ", "002505.SZ"]:
        journal.fail(symbol, "old adapter error")

    with patch("quantradar.datahub.service.AkshareValuationFetcher", return_value=lambda _: []):
        result = DataHubService(config).mvp_health_probe(symbols=["000022.SZ", "002504.SZ", "002505.SZ"])

    assert result["selected"] == {symbol: "FAILED" for symbol in ["000022.SZ", "002504.SZ", "002505.SZ"]}
    assert all(u['category'] == 'UNKNOWN_EMPTY' for u in UpdateJournal(journal.path).data['units'].values())


def test_update_journal_backfills_missing_symbol_error_categories(tmp_path):
    from quantradar.datahub.store import UpdateJournal

    journal = UpdateJournal(tmp_path / "journal.json")
    journal.fail("002504.SZ", "'NoneType' object is not subscriptable", exception_type="TypeError")
    assert journal.classify_unclassified_symbol_errors() == 1
    assert journal.data["units"]["002504.SZ"]["category"] == "SYMBOL_DATA_ERROR"


def test_datahub_cli_exposes_mvp_resume_limit_gap_repair_and_publish_commands():
    from quantradar.datahub.cli import _parser

    backfill = _parser().parse_args(["backfill", "--dataset", "valuation_daily", "--resume", "--limit", "20"])
    assert (backfill.dataset, backfill.resume, backfill.limit) == ("valuation_daily", True, 20)
    assert _parser().parse_args(["gaps"]).command == "gaps"
    assert _parser().parse_args(["repair", "--dataset", "valuation_daily"]).command == "repair"
    assert _parser().parse_args(["publish"]).command == "publish"


def test_datahub_start_reports_unavailable_base_source_as_503(monkeypatch):
    from fastapi import HTTPException
    from pymysql.err import OperationalError
    from quantradar.api.app import datahub_job_start
    from quantradar.datahub.service import DataHubService

    def unavailable(*_args, **_kwargs):
        raise OperationalError(2003, "Can't connect to MySQL server")

    monkeypatch.setattr(DataHubService, "start_job", unavailable)
    with pytest.raises(HTTPException) as error:
        datahub_job_start({})
    assert error.value.status_code == 503
    assert "investment_data unavailable" in str(error.value.detail)


def test_mvp_shard_runner_persists_completed_and_repairs_only_failed_shards(tmp_path):
    from quantradar.datahub.mvp import ShardRunner
    from quantradar.datahub.store import UpdateJournal

    calls = []
    def fetch(symbol):
        calls.append(symbol)
        if symbol == "bad": raise RuntimeError("network")
        if symbol == "old": return None
        return [{"symbol": symbol, "trade_date": "2018-01-02"}]

    journal = UpdateJournal(tmp_path / "journal.json")
    runner = ShardRunner(tmp_path / "stage", journal, fetch)
    report = runner.run(["ok", "old", "bad"], resume=True)
    assert report["completed"] == 1 and report["not_covered"] == 0 and report["failed"] == 2
    calls.clear()
    runner.repair_failed()
    assert set(calls) == {"old", "bad"}


def test_mvp_resume_skips_all_terminal_shard_states(tmp_path):
    from quantradar.datahub.mvp import ShardRunner
    from quantradar.datahub.store import UpdateJournal
    calls = []
    journal = UpdateJournal(tmp_path / "journal.json")
    runner = ShardRunner(tmp_path / "stage", journal, lambda symbol: calls.append(symbol) or [{"symbol": symbol}])
    journal.start("valuation-mvp", dataset="valuation_daily")
    journal.complete("done", raw_sha256="a" * 64, row_count=1)
    journal.gap("old", "NOT_COVERED", "known gap")
    journal.gap("empty", "LEGAL_EMPTY", "legal empty")
    journal.fail("failed", "parse failure")
    runner.run(["done", "old", "empty", "failed"], resume=True)
    assert calls == []


def test_mvp_gap_report_separates_explicit_gaps_and_coverage(tmp_path):
    from quantradar.datahub.mvp import ShardRunner
    from quantradar.datahub.store import UpdateJournal
    journal = UpdateJournal(tmp_path / "journal.json")
    runner = ShardRunner(tmp_path / "stage", journal, lambda _: [{"trade_date": "2018-01-02", "symbol": "ok"}])
    runner.run(["ok"], resume=True)
    journal.gap("old", "NOT_COVERED", "pre-2018")
    journal.fail("bad", "timeout")
    report = runner.gap_report()
    assert report["quality_status"] == "PARTIAL"
    assert report["not_covered_symbols"] == ["old"]
    assert report["failed_symbols"] == ["bad"]


def test_akshare_mvp_adapter_normalizes_a_single_symbol_without_rounding(tmp_path):
    import pandas as pd
    from quantradar.datahub.mvp import AkshareValuationFetcher
    from quantradar.datahub.governor import RequestGovernor

    frame = pd.DataFrame([{"数据日期": "2018-01-02", "PE(TTM)": 1.234567, "市净率": 2.345678, "市销率": 3.456789, "市现率": 4.567891}])
    fetcher = AkshareValuationFetcher(RequestGovernor(tmp_path, "eastmoney", interval_seconds=0), api=lambda _: frame)
    shard = fetcher("600519.SH")
    assert shard.rows[0]["symbol"] == "600519.SH"
    assert shard.rows[0]["pcf_ocf_ttm"] == 4.567891
    assert len(shard.raw_sha256) == 64


def test_adapter_parse_error_fails_one_shard_without_opening_the_upstream_circuit(tmp_path):
    from quantradar.datahub.governor import RequestGovernor
    from quantradar.datahub.mvp import AdapterParseError, AkshareValuationFetcher

    governor = RequestGovernor(tmp_path, "eastmoney", interval_seconds=0, failure_threshold=2)
    fetcher = AkshareValuationFetcher(governor, api=lambda _: (_ for _ in ()).throw(TypeError("'NoneType' object is not subscriptable")))

    with pytest.raises(AdapterParseError) as error:
        fetcher("002504.SZ")

    assert error.value.symbol == "002504.SZ"
    assert error.value.raw_status == "UNAVAILABLE_SDK_EXCEPTION"
    assert governor.status()["circuit_open"] is False
    assert governor.status()["shard_failure_streak"] == 1
    assert governor.status()["upstream_failure_streak"] == 0


def test_shard_runner_persists_adapter_parse_errors_as_symbol_data_errors(tmp_path):
    from quantradar.datahub.mvp import AdapterParseError, ShardRunner
    from quantradar.datahub.store import UpdateJournal

    error = AdapterParseError(symbol="002504.SZ", function="akshare.stock_value_em", adapter_version="test",
                              exception=TypeError("NoneType"), started_at="t0", finished_at="t1")
    journal = UpdateJournal(tmp_path / "journal.json")
    ShardRunner(tmp_path / "stage", journal, lambda _: (_ for _ in ()).throw(error)).run(["002504.SZ"])
    assert journal.data["units"]["002504.SZ"]["category"] == "SYMBOL_DATA_ERROR"


def test_governor_opens_only_for_distinct_source_wide_failures(tmp_path):
    from quantradar.datahub.governor import RequestGovernor

    governor = RequestGovernor(tmp_path, "eastmoney", interval_seconds=0, failure_threshold=2)
    for symbol in ("002504", "002505"):
        with pytest.raises(ConnectionError):
            governor.call(f"valuation_daily/{symbol}", lambda: (_ for _ in ()).throw(ConnectionError("timeout")), max_attempts=1)
    assert governor.status()["circuit_open"] is True
    assert governor.status()["upstream_failure_streak"] == 2


def test_governor_false_positive_resolution_preserves_an_audit_event(tmp_path):
    from quantradar.datahub.governor import RequestGovernor

    governor = RequestGovernor(tmp_path, "eastmoney", interval_seconds=0, failure_threshold=1)
    with pytest.raises(ConnectionError):
        governor.call("valuation_daily/002504", lambda: (_ for _ in ()).throw(ConnectionError("timeout")), max_attempts=1)

    governor.resolve_false_positive(symbol="002504", reason="FALSE_POSITIVE_SYMBOL_PARSE_ERROR")
    ledger = governor.status()
    assert ledger["circuit_open"] is False
    assert ledger["cooldown_until"] is None
    assert ledger["circuit_audit"][-1]["original_symbol"] == "002504"


def test_completed_operation_returns_its_published_release_without_refetching(tmp_path):
    from quantradar.datahub.store import UpdateJournal

    journal = UpdateJournal(tmp_path / "journal.json")
    journal.start("backfill-1", dataset="valuation_daily")
    journal.publish("R123")
    assert UpdateJournal(tmp_path / "journal.json").published_release() == "R123"


def test_service_reuses_a_completed_operation_release_without_calling_sources(tmp_path, monkeypatch):
    from quantradar.config import DataHubConfig
    from quantradar.datahub.release import ReleaseStore
    from quantradar.datahub.service import DataHubService
    from quantradar.datahub.store import UpdateJournal

    config = DataHubConfig(supplemental_repo=str(tmp_path / "repo"), release_root=str(tmp_path / "releases"), raw_root=str(tmp_path / "raw"), journal_root=str(tmp_path / "journal"))
    manifest = ReleaseStore(config.release_root).publish(base_commit="base", supplemental_commit="supp", datasets={}, source_adapters={})
    key = __import__("hashlib").sha256(b'["backfill", "2016-01-01", "2016-01-31", ["600005.SH"]]').hexdigest()[:16]
    journal = UpdateJournal(tmp_path / "journal" / f"backfill-{key}.json")
    journal.start(f"backfill-{key}", dataset="valuation_daily")
    journal.publish(manifest["release_id"])
    monkeypatch.setattr("quantradar.datahub.service.BaostockAdapter", lambda: pytest.fail("source must not be called"))

    assert DataHubService(config).update(mode="backfill", start_date="2016-01-01", end_date="2016-01-31", symbols=["600005.SH"])["release_id"] == manifest["release_id"]


def test_service_records_a_lifecycle_source_failure_in_its_durable_journal(tmp_path, monkeypatch):
    from quantradar.config import DataHubConfig
    from quantradar.datahub.service import DataHubService

    class BrokenBao:
        def __init__(self, **_): pass
        def lifecycle(self): raise RuntimeError("upstream closed")
    monkeypatch.setattr("quantradar.datahub.service.BaostockAdapter", BrokenBao)
    config = DataHubConfig(supplemental_repo=str(tmp_path / "repo"), release_root=str(tmp_path / "releases"), raw_root=str(tmp_path / "raw"), journal_root=str(tmp_path / "journal"))
    with pytest.raises(RuntimeError, match="upstream closed"):
        DataHubService(config).update(mode="backfill", start_date="2016-01-01", end_date="2016-01-31", symbols=["600005.SH"], attempts=1)
    journal = next((tmp_path / "journal").glob("*.json")).read_text()
    assert "security_lifecycle:extract" in journal
    assert "upstream closed" in journal


def test_status_shows_last_failure_before_the_first_release(tmp_path):
    from quantradar.config import DataHubConfig
    from quantradar.datahub.service import DataHubService
    from quantradar.datahub.store import UpdateJournal

    config = DataHubConfig(release_root=str(tmp_path / "releases"), journal_root=str(tmp_path / "journal"))
    journal = UpdateJournal(tmp_path / "journal" / "failed.json")
    journal.start("failed", dataset="security_lifecycle")
    journal.fail("security_lifecycle:extract", "upstream closed")
    assert DataHubService(config).status()["last_failure"]["failures"]["security_lifecycle:extract"] == "upstream closed"


def test_release_reader_pins_both_database_names_to_manifest_commits(tmp_path):
    from quantradar.config import DataHubConfig
    from quantradar.datahub.reader import ReleaseReader
    from quantradar.datahub.release import ReleaseStore

    release = ReleaseStore(tmp_path / "releases").publish(
        base_commit="base-123",
        supplemental_commit="supp-456",
        datasets={},
        source_adapters={},
    )
    reader = ReleaseReader(
        DataHubConfig(
            release_root=str(tmp_path / "releases"),
            supplemental_database="quantradar_data",
        )
    )
    scope = reader.resolve(release["release_id"])
    assert scope.base_database == "investment_data/base-123"
    assert scope.supplemental_database == "quantradar_data/supp-456"
    assert scope.release_id == release["release_id"]

    base = reader.base_config(scope)
    supplemental = reader.supplemental_connection_kwargs(scope)
    assert base.database == "investment_data/base-123"
    assert supplemental["database"] == "quantradar_data/supp-456"
    assert supplemental["port"] == 3308


def test_bootstrap_data_release_activates_the_release_qualified_base_database(tmp_path, monkeypatch):
    from quantradar.config import DataHubConfig
    from quantradar.datahub.release import ReleaseStore
    import quantradar.bootstrap as bootstrap

    manifest = ReleaseStore(tmp_path / "releases").publish(
        base_commit="base-123", supplemental_commit="supp-456", datasets={}, source_adapters={}
    )
    received = {}
    monkeypatch.setattr(bootstrap, "load_datahub_config", lambda: DataHubConfig(release_root=str(tmp_path / "releases")))
    from types import SimpleNamespace
    def activate(config, **_):
        received['config'] = config
        return SimpleNamespace()
    monkeypatch.setattr(bootstrap, "bootstrap_investment_data", activate)

    scope = bootstrap.bootstrap_data_release(manifest["release_id"])
    assert scope.release_id == manifest["release_id"]
    assert received["config"].database == "investment_data/base-123"


def test_commit_qualified_base_connection_checks_the_database_returned_by_dolt(monkeypatch):
    from quantradar.config import InvestmentDataConfig
    from quantradar.providers.investment_data.connection import InvestmentDataConnection

    calls = []
    class Cursor:
        def execute(self, sql, args=()): calls.append((sql, args))
        def fetchone(self): return {"db": "dolt-resolved-base-123"}
        def fetchall(self):
            return [{"TABLE_NAME": name} for name in ("ts_trade_day_calendar", "ts_a_stock_list", "ts_index_weight", "final_a_stock_eod_price", "bao_a_stock_eod_info")]
        def __enter__(self): return self
        def __exit__(self, *_): return False
    class Connection:
        def cursor(self): return Cursor()
    connection = InvestmentDataConnection(InvestmentDataConfig(database="investment_data/base-123"))
    monkeypatch.setattr(connection, "_ensure_connection", lambda: Connection())

    connection.check()
    schema_lookup = calls[-1]
    assert schema_lookup[1][0] == "dolt-resolved-base-123"


def test_snapshot_hash_includes_the_paired_data_release():
    from types import SimpleNamespace
    from quantradar.snapshot import build_snapshot

    engine = SimpleNamespace(daily_records=[{"date": "2016-01-04", "total_value": 100.0}], trades=[], context=SimpleNamespace(portfolio=SimpleNamespace(positions={})), initial_cash=100.0, start_date="2016-01-04", end_date="2016-01-04", frequency="day")
    base_env = {"dolt_commit": "base-1", "provider_version": "1", "data_release": {"release_id": "R-one", "base_commit": "base-1", "supplemental_commit": "supp-1"}}
    newer_env = {**base_env, "data_release": {"release_id": "R-two", "base_commit": "base-1", "supplemental_commit": "supp-2"}}
    first = build_snapshot(engine, audit_env=base_env)
    second = build_snapshot(engine, audit_env=newer_env)
    assert first["environment"]["data_release"]["release_id"] == "R-one"
    assert first["snapshot_hash"] != second["snapshot_hash"]


def test_research_sample_reads_base_and_supplemental_under_one_release():
    from types import SimpleNamespace
    from quantradar.datahub.sample import run_research_sample

    class Base:
        def query_one(self, *_): return {"symbol": "600005.SH", "tradedate": "2016-01-04", "close": 3.23, "turn": 0.49, "is_st": 0, "tradestatus": 1}
    class Supplemental:
        def valuation(self, *_args, **_kwargs): return {"rows": [{"pe_ttm": -43.8, "pb_mrq": 0.9, "ps_ttm": 0.4, "pcf_ncf_ttm": 34.8}], "pit_status": "PARTIAL"}
        def industry_as_of(self, *_): return {"industry_code": "440000", "pit_status": "PARTIAL"}
        def lifecycle_as_of(self, *_): return {"list_date": "1999-08-03", "delist_date": "2017-02-14", "status": "DELISTED", "pit_status": "PARTIAL"}
    class Reader:
        def resolve(self, *_): return SimpleNamespace(release_id="R123", manifest={"base_commit": "base", "supplemental_commit": "supp"})
        def base_connection(self, *_): return Base()
        def supplemental_reader(self, *_): return Supplemental()

    result = run_research_sample(Reader(), release_id="R123", symbol="600005.SH", as_of="2016-01-04")
    assert result["base"]["turn"] == 0.49
    assert result["valuation"]["pe_ttm"] == -43.8
    assert result["industry"]["industry_code"] == "440000"
    assert result["result_hash"]


def test_supplemental_reader_rejects_required_missing_values_and_marks_optional_partial():
    from quantradar.datahub.reader import SupplementalReader

    class Cursor:
        def execute(self, *_): pass
        def fetchall(self):
            return [{"trade_date": "2016-01-04", "pe_ttm": 12.0, "pb_mrq": None, "ps_ttm": 2.0, "pcf_ncf_ttm": 4.0, "pit_status": "PARTIAL"}]
        def __enter__(self): return self
        def __exit__(self, *_): return False
    class Connection:
        def cursor(self): return Cursor()
        def close(self): pass

    reader = SupplementalReader(lambda: Connection())
    with pytest.raises(ValueError, match="required supplemental fields missing"):
        reader.valuation("600005.SH", "2016-01-04", "2016-01-04", required_fields=("pb_mrq",))
    partial = reader.valuation("600005.SH", "2016-01-04", "2016-01-04", required_fields=())
    assert partial["pit_status"] == "PARTIAL"
    assert partial["excluded_samples"] == 1


def test_supplemental_store_uses_dataset_keys_and_commits_only_its_database():
    from quantradar.datahub.dolt import SupplementalStore

    executed: list[tuple[str, object]] = []

    class Cursor:
        def execute(self, sql, args=()):
            executed.append((sql, args))

        def fetchone(self):
            return {"commit_hash": "supp-commit"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    class Connection:
        def cursor(self):
            return Cursor()

        def commit(self):
            executed.append(("PYMYSQL_COMMIT", ()))

    store = SupplementalStore(Connection())
    store.ensure_schema()
    store.upsert_valuations(
        [{"trade_date": "2016-01-04", "symbol": "600005.SH", "pe_ttm": -43.0, "pb_mrq": 1.0, "ps_ttm": None, "pcf_ncf_ttm": 2.0,
          "source": "baostock", "raw_sha256": "a" * 64, "adapter_version": "adapter", "fetched_at": "t", "available_date": None, "pit_status": "PARTIAL"}]
    )
    assert any("qr_valuation_daily" in sql and "ON DUPLICATE KEY UPDATE" in sql for sql, _ in executed)
    assert store.commit("test update") == "supp-commit"
    assert any("DOLT_COMMIT" in sql for sql, _ in executed)


def test_pipeline_leaves_current_release_untouched_when_one_dataset_fails(tmp_path):
    from quantradar.datahub.pipeline import DataHubPipeline, UpdateFailure
    from quantradar.datahub.release import ReleaseStore

    releases = ReleaseStore(tmp_path / "releases")
    old = releases.publish(base_commit="base-old", supplemental_commit="supp-old", datasets={}, source_adapters={})

    class Writer:
        def ensure_schema(self): pass
        def upsert_valuations(self, rows): pass
        def upsert_industries(self, rows): pass
        def upsert_lifecycles(self, rows): pass
        def commit(self, _): return "supp-new"

    pipeline = DataHubPipeline(tmp_path / "runtime", releases=releases, writer=Writer(), base_commit=lambda: "base-new")
    with pytest.raises(UpdateFailure, match="sw_industry_history"):
        pipeline.publish(
            {
                "valuation_daily": lambda: [],
                "sw_industry_history": lambda: (_ for _ in ()).throw(RuntimeError("source down")),
                "security_lifecycle": lambda: [],
            }
        )
    assert releases.current()["release_id"] == old["release_id"]


def test_pipeline_quality_gate_rejects_an_empty_required_dataset_before_writer_mutation(tmp_path):
    from quantradar.datahub.pipeline import DataHubPipeline, UpdateFailure
    from quantradar.datahub.release import ReleaseStore

    calls = []
    class Writer:
        def ensure_schema(self): calls.append("schema")
    releases = ReleaseStore(tmp_path / "releases")
    old = releases.publish(base_commit="old-base", supplemental_commit="old-supp", datasets={}, source_adapters={})
    pipeline = DataHubPipeline(tmp_path / "runtime", releases=releases, writer=Writer(), base_commit=lambda: "base")
    with pytest.raises(UpdateFailure, match="quality gate.*valuation_daily.*no rows"):
        pipeline.publish({"valuation_daily": lambda: [], "sw_industry_history": lambda: [{"effective_from": "2016-01-04"}], "security_lifecycle": lambda: [{"list_date": "2016-01-04"}]})
    assert calls == []
    assert releases.current()["release_id"] == old["release_id"]


def test_pipeline_publishes_a_pair_only_after_all_datasets_and_writer_commit(tmp_path):
    from quantradar.datahub.pipeline import DataHubPipeline
    from quantradar.datahub.release import ReleaseStore

    calls: list[str] = []
    class Writer:
        def ensure_schema(self): calls.append("schema")
        def upsert_valuations(self, rows): calls.append(f"valuation:{len(rows)}")
        def upsert_industries(self, rows): calls.append(f"industry:{len(rows)}")
        def upsert_lifecycles(self, rows): calls.append(f"lifecycle:{len(rows)}")
        def commit(self, message): calls.append("commit"); return "supp-new"

    pipeline = DataHubPipeline(tmp_path / "runtime", releases=ReleaseStore(tmp_path / "releases"), writer=Writer(), base_commit=lambda: "base-new")
    manifest = pipeline.publish(
        {
            "valuation_daily": lambda: [{"trade_date": "2016-01-04"}],
            "sw_industry_history": lambda: [{"effective_from": "2016-01-04"}],
            "security_lifecycle": lambda: [{"list_date": "2016-01-04"}],
        }
    )
    assert calls == ["schema", "valuation:1", "industry:1", "lifecycle:1", "commit"]
    assert manifest["base_commit"] == "base-new"
    assert manifest["supplemental_commit"] == "supp-new"
    assert manifest["datasets"]["valuation_daily"]["first_date"] == "2016-01-04"
    assert manifest["datasets"]["valuation_daily"]["stocks"] == 0


def test_pipeline_records_dolt_history_revisions_in_the_release_manifest(tmp_path):
    from quantradar.datahub.pipeline import DataHubPipeline
    from quantradar.datahub.release import ReleaseStore

    class Writer:
        def ensure_schema(self): pass
        def upsert_valuations(self, _): pass
        def upsert_industries(self, _): pass
        def upsert_lifecycles(self, _): pass
        def commit(self, _): return "supp-new"
        def revision_counts(self, _): return {"valuation_daily": 2, "sw_industry_history": 0, "security_lifecycle": 1}

    manifest = DataHubPipeline(
        tmp_path / "runtime", releases=ReleaseStore(tmp_path / "releases"), writer=Writer(), base_commit=lambda: "base-new"
    ).publish({
        "valuation_daily": lambda: [{"trade_date": "2016-01-04"}],
        "sw_industry_history": lambda: [{"effective_from": "2016-01-04"}],
        "security_lifecycle": lambda: [{"list_date": "2016-01-04"}],
    })
    assert manifest["datasets"]["valuation_daily"]["history_revision_count"] == 2
    assert manifest["datasets"]["security_lifecycle"]["history_revision_count"] == 1


def test_pipeline_persists_source_bytes_before_writer_is_called(tmp_path):
    from quantradar.datahub.adapters import FetchedRows
    from quantradar.datahub.pipeline import DataHubPipeline
    from quantradar.datahub.release import ReleaseStore
    from quantradar.datahub.store import RawStore

    calls: list[str] = []
    class Writer:
        def ensure_schema(self): calls.append("schema")
        def upsert_valuations(self, rows): calls.append("valuation")
        def upsert_industries(self, rows): calls.append("industry")
        def upsert_lifecycles(self, rows): calls.append("lifecycle")
        def commit(self, _): return "supp"

    pipeline = DataHubPipeline(tmp_path / "runtime", releases=ReleaseStore(tmp_path / "releases"), writer=Writer(), base_commit=lambda: "base", raw_store=RawStore(tmp_path / "raw"))
    result = FetchedRows("valuation_daily", b"raw", [{"trade_date": "2016-01-04"}], "baostock", "2026-09-09T00:00:00+00:00")
    pipeline.publish(
        {
            "valuation_daily": lambda: result,
            "sw_industry_history": lambda: [{"effective_from": "2016-01-04"}],
            "security_lifecycle": lambda: [{"list_date": "2016-01-04"}],
        }
    )
    raw_dir = tmp_path / "raw" / "raw"
    assert len(list(raw_dir.iterdir())) == 1
    assert next(raw_dir.iterdir()).read_bytes() == b"raw"
    assert calls[0] == "schema"


def test_lifecycle_source_filters_only_shanghai_and_shenzhen_a_shares():
    from quantradar.datahub.adapters import sh_sz_a_lifecycle_rows

    rows = sh_sz_a_lifecycle_rows(
        [
            {"code": "sh.600005", "type": "1", "status": "0"},
            {"code": "sz.000001", "type": "1", "status": "1"},
            {"code": "sh.000001", "type": "2", "status": "1"},
            {"code": "sz.159001", "type": "5", "status": "1"},
            {"code": "bj.920001", "type": "1", "status": "1"},
        ]
    )
    assert [row["code"] for row in rows] == ["sh.600005", "sz.000001"]


def test_baostock_row_reader_rejects_an_unbounded_result_stream():
    from quantradar.datahub.adapters import BaostockAdapter

    class InfiniteResult:
        error_code = "0"
        error_msg = ""
        fields = ["code"]
        def next(self): return True
        def get_row_data(self): return ["sh.600005"]

    with pytest.raises(RuntimeError, match="row limit"):
        BaostockAdapter._rows(InfiniteResult(), max_rows=3)


def test_baostock_batch_uses_one_authenticated_session_for_many_symbols(monkeypatch):
    from contextlib import contextmanager
    from quantradar.datahub.adapters import BaostockAdapter

    class Result:
        error_code = "0"
        error_msg = ""
        fields = ["date", "code", "peTTM", "pbMRQ", "psTTM", "pcfNcfTTM"]
        def __init__(self, code): self.code, self.done = code, False
        def next(self):
            if self.done: return False
            self.done = True
            return True
        def get_row_data(self): return ["2016-01-04", self.code, "1", "2", "3", "4"]

    class Client:
        def __init__(self): self.calls = []
        def query_history_k_data_plus(self, code, *_args, **_kwargs):
            self.calls.append(code)
            return Result(code)

    client = Client()
    entered = []
    @contextmanager
    def session():
        entered.append(True)
        yield client

    adapter = BaostockAdapter()
    monkeypatch.setattr(adapter, "_session", session)
    rows = list(adapter.valuations(["600005.SH", "600519.SH"], "2016-01-01", "2016-01-31"))
    assert [symbol for symbol, _ in rows] == ["600005.SH", "600519.SH"]
    assert client.calls == ["sh.600005", "sh.600519"]
    assert entered == [True]


def test_baostock_eof_socket_turns_an_empty_recv_into_a_finite_error():
    from quantradar.datahub.adapters import _EofFailingSocket

    class Socket:
        def recv(self, _): return b""

    with pytest.raises(ConnectionError, match="closed"):
        _EofFailingSocket(Socket()).recv(8192)


def test_repair_clears_pause_and_preserves_completed_shards(tmp_path):
    from quantradar.config import DataHubConfig
    from quantradar.datahub.service import DataHubService
    from quantradar.datahub.store import UpdateJournal
    config = DataHubConfig(supplemental_repo=str(tmp_path), raw_root=str(tmp_path / 'raw'), journal_root=str(tmp_path / 'journals'))
    journal = UpdateJournal(tmp_path / 'journals' / 'valuation_daily-mvp.json')
    journal.complete('good', raw_sha256='a' * 64, row_count=42)
    journal.fail('bad', 'source error')
    journal.request_pause()
    calls = []
    def fetch(symbol):
        calls.append(symbol)
        return [{'symbol': symbol, 'trade_date': '2026-09-10'}]
    with patch('quantradar.datahub.service.AkshareValuationFetcher', return_value=fetch):
        result = DataHubService(config).mvp_repair(dataset='valuation_daily')
    saved = UpdateJournal(journal.path).data
    assert calls == ['bad']
    assert result['failed'] == 0
    assert saved['units']['good']['row_count'] == 42
    assert saved['phases']['download']['status'] == 'DONE'
    assert saved['heartbeat']['pid'] == 0
    assert saved['repair_attempts'][-1]['result']['completed'] == 2


def test_published_valuation_with_no_rows_is_not_reported_as_pass(monkeypatch):
    from quantradar.datahub.reader import SupplementalReader
    reader = SupplementalReader(lambda: None)
    monkeypatch.setattr(reader, '_query', lambda *_: [])
    with pytest.raises(ValueError, match='no published valuation data'):
        reader.valuation('600000.SH', '2020-01-01', '2020-01-02')


def test_legacy_publication_uses_daily_candidate_checks(tmp_path, monkeypatch):
    from quantradar.config import DataHubConfig
    from quantradar.datahub.service import DataHubService
    from quantradar.datahub.store import UpdateJournal
    service = DataHubService(DataHubConfig(journal_root=str(tmp_path), raw_root=str(tmp_path / 'raw')))
    journal = UpdateJournal(tmp_path / 'valuation_daily-mvp.json')
    journal.record_repair({'failed': 196})
    from quantradar.datahub.daily import DailyUpdate
    monkeypatch.setattr(DailyUpdate, 'start', lambda self, mode: {'mode': mode})
    assert service.mvp_publish() == {'mode': 'publish'}
