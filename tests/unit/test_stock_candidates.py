import json

from quantradar.datahub.adapters import FetchedRows
from quantradar.datahub.stock_candidates import collect_stock_daily_candidates, promote_stock_candidate_raw, replay_stock_daily_candidates_from_raw
from quantradar.datahub.store import RawStore


def test_stock_candidate_stages_exact_sessions_and_raw_receipt(tmp_path):
    price = [
        {"trade_date": "2024-01-02", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 100, "amount": 200,
         "adapter_version": "test", "raw_sha256": "ignored"},
        {"trade_date": "2024-01-03", "open": 2, "high": 3, "low": 2, "close": 3, "volume": 100, "amount": 300,
         "adapter_version": "test", "raw_sha256": "ignored"},
    ]
    status = [{"trade_date": row["trade_date"], "tradestatus": 1, "is_st": 0} for row in price]
    class Adapter:
        def daily_bundles(self, *_args, **_kwargs):
            yield "000009.SZ", FetchedRows("trade_status_daily", b"raw", status, "baostock", "now",
                candidate_domains={"price": price, "trade_status": status}, evidence_level="SDK_RESPONSE_SNAPSHOT")
    outcome = collect_stock_daily_candidates(tmp_path, ["000009.SZ"], "2024-01-02", "2024-01-03",
        expected_days={"000009.SZ": ["2024-01-02", "2024-01-03"]}, adapter=Adapter())
    assert outcome["status"] == "COMPLETE"
    staged = json.loads((tmp_path / "stock-daily-candidates" / "000009.SZ.json").read_text())
    assert staged["price"][0]["volume_shares"] == 100
    assert staged["qualification"] == "CANDIDATE_NOT_PUBLISHED"
    promoted = promote_stock_candidate_raw(tmp_path, tmp_path / "durable")
    assert promoted["symbols"] == ["000009.SZ"]
    digest = json.loads((tmp_path / "journals" / "stock-daily-candidates.json").read_text())["units"]["000009.SZ"]["raw_sha256"]
    assert (tmp_path / "durable" / "raw" / digest).is_file()


def test_stock_candidate_rejects_missing_session_without_completion(tmp_path):
    class Adapter:
        def daily_bundles(self, *_args, **_kwargs):
            row = {"trade_date": "2024-01-02", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1, "amount": 1,
                   "adapter_version": "test", "raw_sha256": "ignored"}
            yield "000009.SZ", FetchedRows("x", b"raw", [], "baostock", "now",
                candidate_domains={"price": [row], "trade_status": [{"trade_date": "2024-01-02", "tradestatus": 1, "is_st": 0}]})
    outcome = collect_stock_daily_candidates(tmp_path, ["000009.SZ"], "2024-01-02", "2024-01-03",
        expected_days={"000009.SZ": ["2024-01-02", "2024-01-03"]}, adapter=Adapter())
    assert outcome["status"] == "PARTIAL"
    assert "000009.SZ" in outcome["failed"]


def test_stock_candidate_keeps_valid_status_when_price_fields_are_missing(tmp_path):
    class Adapter:
        def daily_bundles(self, *_args, **_kwargs):
            row = {"trade_date": "2024-01-02", "open": None, "high": None, "low": None, "close": None, "volume": None, "amount": None,
                   "adapter_version": "test", "raw_sha256": "ignored"}
            yield "000009.SZ", FetchedRows("x", b"raw", [], "baostock", "now",
                candidate_domains={"price": [row], "trade_status": [{"trade_date": "2024-01-02", "tradestatus": 0, "is_st": 0}]})
    outcome = collect_stock_daily_candidates(tmp_path, ["000009.SZ"], "2024-01-02", "2024-01-02",
        expected_days={"000009.SZ": ["2024-01-02"]}, adapter=Adapter())
    assert outcome["status"] == "COMPLETE"
    staged = json.loads((tmp_path / "stock-daily-candidates" / "000009.SZ.json").read_text())
    assert staged["price"] == []
    assert staged["price_qualification"] == "MISSING_OHLCV_OR_AMOUNT"


def test_stock_candidate_replays_captured_raw_without_source_call(tmp_path):
    content = b"date,code,open,high,low,close,volume,amount,turn,tradestatus,isST\n2024-01-02,sz.000009,,,,,,,0,0,0\n"
    durable = tmp_path / "durable"
    digest = RawStore(durable).put("test", content)["sha256"]
    outcome = replay_stock_daily_candidates_from_raw(tmp_path, ["000009.SZ"], "2024-01-02", "2024-01-02",
        expected_days={"000009.SZ": ["2024-01-02"]}, raw_hashes={"000009.SZ": digest}, durable_raw_root=durable)
    assert outcome["status"] == "COMPLETE"
    staged = json.loads((tmp_path / "stock-daily-candidates" / "000009.SZ.json").read_text())
    assert staged["price_qualification"] == "MISSING_OHLCV_OR_AMOUNT"
