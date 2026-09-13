import json

from quantradar.datahub.adapters import FetchedRows
from quantradar.datahub.stock_candidates import collect_stock_daily_candidates, promote_stock_candidate_raw


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
