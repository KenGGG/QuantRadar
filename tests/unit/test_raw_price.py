import pandas as pd

from quantradar.datahub.raw_price import raw_price_readiness, resolve_raw_price


def test_raw_resolver_prefers_final_and_repairs_only_absent_final_rows():
    final = pd.DataFrame({"open": [10.0], "high": [11.0], "low": [9.0], "close": [10.0], "volume": [2.0], "amount": [20.0]}, index=pd.to_datetime(["2020-08-18"]))
    bao = pd.DataFrame({"open": [1.0, 10.0], "high": [2.0, 11.0], "low": [1.0, 9.0], "close": [2.0, 10.0], "volume": [100.0, 999.0], "amount": [200.0, 9999.0]}, index=pd.to_datetime(["2020-08-19", "2020-08-18"]))
    resolved = resolve_raw_price(final, bao, symbol="000039.SZ")
    assert resolved["source_table"].tolist() == ["final_a_stock_eod_price", "bao_a_stock_eod_info"]
    assert resolved.loc[0, "volume"] == 200 and resolved.loc[0, "amount"] == 20000
    assert resolved.loc[1, "repair_reason"] == "FINAL_ROW_MISSING"
    assert resolved.loc[1, "volume"] == 100 and resolved.loc[1, "amount"] == 200


def test_raw_resolver_never_reports_adjusted_or_account_ready():
    rows = [{"open": 1, "high": 1, "low": 1, "close": 1, "volume": 0, "amount": 0}]
    assert raw_price_readiness(rows) == {"raw_price_ready": True, "adjusted_price_ready": False,
                                         "corporate_action_ready": False, "account_replay_ready": False,
                                         "price_mode": "RAW"}
