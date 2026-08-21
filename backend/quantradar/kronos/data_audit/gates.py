from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import GateEvidence


_REQUIRED_EVIDENCE = (
    "price_semantics",
    "corporate_action",
    "pit_universe",
    "latest_tradeability",
)


def derive_latest_tradeability_evidence(
    coverage_rows: list[dict[str, Any]],
) -> GateEvidence:
    by_dataset = {str(row["dataset"]): row for row in coverage_rows}
    price_date = by_dataset.get("price", {}).get("max_date")
    required = (
        "index_constituents",
        "up_down_limits",
        "st",
        "tradestatus_paused",
        "corporate_action_proxy",
        "stock_master",
    )
    missing = [name for name in required if by_dataset.get(name, {}).get("max_date") is None]
    if price_date is None or missing:
        details = ", ".join(missing) if missing else "price"
        return GateEvidence.blocked(
            f"Missing latest coverage for: {details}", "coverage.csv"
        )
    stale = [
        f"{name}={by_dataset[name]['max_date']} < price={price_date}"
        for name in required
        if by_dataset[name]["max_date"] < price_date
    ]
    if stale:
        return GateEvidence.partial("; ".join(stale), "coverage.csv")
    return GateEvidence.pass_("coverage.csv")


def derive_data_gates(evidence: Mapping[str, GateEvidence]) -> dict[str, Any]:
    missing = [name for name in _REQUIRED_EVIDENCE if name not in evidence]
    if missing:
        raise ValueError(f"missing gate evidence: {', '.join(missing)}")

    price_ready = evidence["price_semantics"].ready
    action_ready = evidence["corporate_action"].ready
    pit_ready = evidence["pit_universe"].ready
    tradeability_ready = evidence["latest_tradeability"].ready
    signal_ready = price_ready and pit_ready
    formal_ready = signal_ready and action_ready and tradeability_ready

    return {
        "price_semantics_ready": price_ready,
        "corporate_action_ready": action_ready,
        "pit_universe_ready": pit_ready,
        "latest_tradeability_ready": tradeability_ready,
        "signal_research_ready": signal_ready,
        "formal_backtest_ready": formal_ready,
        "real_assist_data_ready": formal_ready,
        "gates": {name: evidence[name].as_dict() for name in _REQUIRED_EVIDENCE},
    }
