import json

import pytest

from quantradar.datahub.stock_events import parse_cninfo_dividend


def _payload(**values):
    row = {
        "F006D": "2022-06-01", "F044V": "现金分红", "F010N": "0",
        "F011N": "0", "F012N": "6", "F018D": "2022-06-08",
        "F020D": "2022-06-09", "F023D": "2022-06-09", "F025D": None,
        "F007V": "每10股派6元", "F001V": "2021-12-31",
    }
    row.update(values)
    return json.dumps({"records": [row]}, ensure_ascii=False).encode()


def test_cninfo_dividend_preserves_implementation_fields_and_per_ten_basis():
    event = parse_cninfo_dividend(_payload(), symbol="600519")[0]
    assert event["cash_per_ten"] == 6.0
    assert event["cash_per_share"] == 0.6
    assert event["share_multiplier"] == 1.0
    assert event["available_date"] == "2022-06-01"
    assert event["report_period"] == "2021-12-31"
    assert event["pit_status"] == "PARTIAL"


def test_cninfo_dividend_does_not_fill_missing_share_component_with_zero():
    event = parse_cninfo_dividend(_payload(F011N=None), symbol="600519")[0]
    assert event["capitalization_shares_per_ten"] is None
    assert event["share_multiplier"] is None


def test_cninfo_report_period_is_not_coerced_to_a_date():
    event = parse_cninfo_dividend(_payload(F001V="2025年报"), symbol="600519")[0]
    assert event["report_period"] == "2025年报"


def test_cninfo_dividend_rejects_bad_identity_and_missing_required_schema():
    with pytest.raises(ValueError, match="A-share"):
        parse_cninfo_dividend(_payload(), symbol="900001")
    with pytest.raises(ValueError, match="records"):
        parse_cninfo_dividend(b"{}", symbol="600519")
    with pytest.raises(ValueError, match="announcement"):
        parse_cninfo_dividend(_payload(F006D=None), symbol="600519")
