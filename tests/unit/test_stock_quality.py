import pytest

from quantradar.datahub.stock_quality import reconcile_stock_sample


def test_stock_sample_reconciliation_proves_share_yuan_scaling():
    candidate = [{"symbol": "000009.SZ", "trade_date": "2024-01-02", "open": 1, "high": 2, "low": 1, "close": 2,
                  "volume_shares": 12_300, "amount_cny": 45_600}]
    reference = [{"symbol": "000009.SZ", "trade_date": "2024-01-02", "open": 1, "high": 2, "low": 1, "close": 2,
                  "volume": 123, "amount": 45.6}]
    assert reconcile_stock_sample(candidate, reference)["status"] == "PASS"


def test_stock_sample_reconciliation_rejects_different_keys_and_values():
    candidate = [{"symbol": "000009.SZ", "trade_date": "2024-01-02", "open": 1, "high": 2, "low": 1, "close": 2,
                  "volume_shares": 12_300, "amount_cny": 45_600}]
    reference = [{"symbol": "000009.SZ", "trade_date": "2024-01-02", "open": 1, "high": 2, "low": 1, "close": 2,
                  "volume": 122, "amount": 45.6}]
    assert reconcile_stock_sample(candidate, reference)["status"] == "FAIL"
    with pytest.raises(ValueError):
        reconcile_stock_sample(candidate, [])


def test_stock_sample_reconciliation_allows_only_frozen_display_rounding():
    candidate = [{"symbol": "000009.SZ", "trade_date": "2024-01-02", "open": 1, "high": 2, "low": 1, "close": 2,
                  "volume_shares": 12_324, "amount_cny": 45_600}]
    reference = [{"symbol": "000009.SZ", "trade_date": "2024-01-02", "open": 1, "high": 2, "low": 1, "close": 2,
                  "volume": 123, "amount": 45.6}]
    assert reconcile_stock_sample(candidate, reference)["status"] == "PASS"
    candidate[0]["volume_shares"] = 12_351
    assert reconcile_stock_sample(candidate, reference)["status"] == "FAIL"
