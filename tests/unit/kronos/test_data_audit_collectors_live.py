from __future__ import annotations

import pytest

from quantradar.config import load_investment_data_config
from quantradar.kronos.data_audit.actions import audit_corporate_actions
from quantradar.kronos.data_audit.prices import audit_price_semantics
from quantradar.kronos.data_audit.schema import audit_schema_and_coverage
from quantradar.kronos.data_audit.universe import audit_pit_universe
from quantradar.providers.investment_data.connection import InvestmentDataConnection
from quantradar.providers.investment_data.provider import InvestmentDataProvider

pytestmark = [pytest.mark.unit, pytest.mark.requires_dolt]


@pytest.fixture(scope="module")
def audit_context():
    config = load_investment_data_config()
    connection = InvestmentDataConnection(config)
    provider = InvestmentDataProvider(config)
    try:
        yield connection, provider
    finally:
        connection.close()


@pytest.fixture(scope="module")
def price_audit(audit_context):
    connection, provider = audit_context
    return audit_price_semantics(connection, provider, min_samples=30)


def test_real_schema_uses_actual_calendar_date_column_and_reports_all_datasets(db_connection):
    result = audit_schema_and_coverage(db_connection)

    calendar_columns = {
        column["name"] for column in result["schemas"]["ts_trade_day_calendar"]
    }
    assert "date" in calendar_columns
    assert "cal_date" not in calendar_columns
    assert {row["dataset"] for row in result["coverage"]} == {
        "price",
        "index_constituents",
        "up_down_limits",
        "st",
        "tradestatus_paused",
        "corporate_action_proxy",
        "stock_master",
        "trade_calendar",
    }


def test_real_price_audit_reconciles_thirty_diverse_symbols(price_audit):
    assert len(price_audit["rows"]) >= 30
    assert {row["board"] for row in price_audit["rows"]} >= {
        "SH_MAIN",
        "SZ_MAIN",
        "CHINEXT",
        "STAR",
    }
    assert all(row["status"] == "PASS" for row in price_audit["rows"])
    assert max(row["years_covered"] for row in price_audit["rows"]) >= 8
    assert any(row["has_zero_volume_history"] for row in price_audit["rows"])


def test_real_corporate_action_audit_keeps_missing_authoritative_fields_partial(
    audit_context, price_audit
):
    db_connection, _ = audit_context
    symbols = [row["internal_symbol"] for row in price_audit["rows"]]
    result = audit_corporate_actions(db_connection, symbols, min_events=20)

    assert len(result["rows"]) >= 20
    assert result["evidence"].status.value == "PARTIAL"
    assert all(row["authoritative_event_type"] is False for row in result["rows"])
    assert all(row["accounting_verified"] is False for row in result["rows"])


def test_real_pit_audit_uses_twenty_non_future_historical_snapshots(
    db_connection, live_provider
):
    result = audit_pit_universe(db_connection, live_provider, min_weeks=20)

    assert len(result["rows"]) == 20
    assert all(row["snapshot_not_future"] for row in result["rows"])
    assert all(row["status"] == "PASS" for row in result["rows"])
