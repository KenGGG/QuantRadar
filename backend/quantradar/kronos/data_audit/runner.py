from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from pathlib import Path
from typing import Any

from quantradar.audit import dolt_head_commit

from .actions import audit_corporate_actions
from .gates import (
    derive_data_gates,
    derive_latest_tradeability_evidence,
    derive_pit_universe_evidence,
)
from .prices import audit_price_semantics
from .report import publish_audit_reports
from .schema import audit_schema_and_coverage
from .universe import audit_pit_universe


class DataVersionChangedError(RuntimeError):
    pass


def collect_audit_evidence(connection, provider) -> dict[str, Any]:
    schema = audit_schema_and_coverage(connection)
    prices = audit_price_semantics(connection, provider, min_samples=30)
    symbols = [row["internal_symbol"] for row in prices["rows"]]
    actions = audit_corporate_actions(connection, symbols, min_events=20)
    universe = audit_pit_universe(connection, provider, min_weeks=20)
    return {
        "schema": schema,
        "prices": prices,
        "actions": actions,
        "universe": universe,
    }


def run_data_audit(
    connection,
    provider,
    output_dir: str | Path,
    *,
    collect_fn: Callable[[Any, Any], dict[str, Any]] = collect_audit_evidence,
    generated_at: dt.datetime | None = None,
) -> dict[str, Any]:
    start_commit = dolt_head_commit(connection)
    if not start_commit:
        raise RuntimeError("Unable to read the starting Dolt HEAD")
    bundle = collect_fn(connection, provider)
    end_commit = dolt_head_commit(connection)
    if not end_commit:
        raise RuntimeError("Unable to read the ending Dolt HEAD")
    if start_commit != end_commit:
        raise DataVersionChangedError(
            f"Dolt HEAD changed during audit: {start_commit} -> {end_commit}"
        )
    evidence = {
        "price_semantics": bundle["prices"]["evidence"],
        "corporate_action": bundle["actions"]["evidence"],
        "pit_universe": derive_pit_universe_evidence(
            bundle["universe"]["evidence"], bundle["schema"]["coverage"]
        ),
        "latest_tradeability": derive_latest_tradeability_evidence(
            bundle["schema"]["coverage"]
        ),
    }
    gates = {**derive_data_gates(evidence), "data_commit": start_commit}
    generated_at = generated_at or dt.datetime.now(dt.timezone.utc)
    manifest = publish_audit_reports(
        bundle,
        gates,
        output_dir=output_dir,
        start_commit=start_commit,
        end_commit=end_commit,
        generated_at=generated_at,
    )
    return {
        "output_dir": str(Path(output_dir)),
        "manifest": manifest,
        "gates": gates,
    }
