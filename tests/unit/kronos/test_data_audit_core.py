from __future__ import annotations

import datetime as dt
from decimal import Decimal

from quantradar.kronos.data_audit.gates import derive_data_gates
from quantradar.kronos.data_audit.models import AuditStatus, GateEvidence, json_safe


def test_json_safe_converts_database_scalars_without_losing_structure():
    value = {
        "day": dt.date(2026, 8, 18),
        "created": dt.datetime(2026, 8, 21, 9, 30, tzinfo=dt.timezone.utc),
        "ratio": Decimal("0.125"),
        "nested": (AuditStatus.PARTIAL, {"ready": False}),
    }

    assert json_safe(value) == {
        "day": "2026-08-18",
        "created": "2026-08-21T09:30:00+00:00",
        "ratio": 0.125,
        "nested": ["PARTIAL", {"ready": False}],
    }


def test_formal_and_real_assist_stay_blocked_without_corporate_action_evidence():
    evidence = {
        "price_semantics": GateEvidence.pass_("prices.csv"),
        "corporate_action": GateEvidence.partial(
            "No authoritative event type or share-change fields", "actions.csv"
        ),
        "pit_universe": GateEvidence.pass_("pit.csv"),
        "latest_tradeability": GateEvidence.partial(
            "ST and limits lag the latest price", "coverage.csv"
        ),
    }

    result = derive_data_gates(evidence)

    assert result["price_semantics_ready"] is True
    assert result["corporate_action_ready"] is False
    assert result["pit_universe_ready"] is True
    assert result["latest_tradeability_ready"] is False
    assert result["signal_research_ready"] is True
    assert result["formal_backtest_ready"] is False
    assert result["real_assist_data_ready"] is False
    assert result["gates"]["corporate_action"]["status"] == "PARTIAL"
    assert result["gates"]["corporate_action"]["evidence_files"] == ["actions.csv"]


def test_failed_price_semantics_blocks_every_downstream_readiness_gate():
    evidence = {
        "price_semantics": GateEvidence.fail("adjusted close mismatch", "prices.csv"),
        "corporate_action": GateEvidence.pass_("actions.csv"),
        "pit_universe": GateEvidence.pass_("pit.csv"),
        "latest_tradeability": GateEvidence.pass_("coverage.csv"),
    }

    result = derive_data_gates(evidence)

    assert result["price_semantics_ready"] is False
    assert result["signal_research_ready"] is False
    assert result["formal_backtest_ready"] is False
    assert result["real_assist_data_ready"] is False
