from __future__ import annotations

from typing import Any

from .models import GateEvidence


def detect_action_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    previous_by_symbol: dict[str, dict[str, Any]] = {}
    for row in sorted(rows, key=lambda item: (str(item["symbol"]), item["tradedate"])):
        symbol = str(row["symbol"])
        previous = previous_by_symbol.get(symbol)
        previous_by_symbol[symbol] = row
        if previous is None:
            continue
        before_factor = previous.get("adjfactor")
        after_factor = row.get("adjfactor")
        preclose = row.get("preclose")
        previous_close = previous.get("close")
        if None in (before_factor, after_factor, preclose, previous_close):
            continue
        factor_ratio = float(after_factor) / float(before_factor) if float(before_factor) else 0.0
        preclose_gap = float(previous_close) - float(preclose)
        if abs(factor_ratio - 1.0) <= 1e-8 and abs(preclose_gap) <= 1e-8:
            continue
        events.append(
            {
                "symbol": symbol,
                "previous_date": previous["tradedate"],
                "ex_date": row["tradedate"],
                "previous_close": float(previous_close),
                "preclose": float(preclose),
                "preclose_gap_proxy": preclose_gap,
                "factor_before": float(before_factor),
                "factor_after": float(after_factor),
                "factor_ratio": factor_ratio,
                "shares_before": None,
                "shares_after": None,
                "cash_delta": None,
                "cost_basis_after": None,
                "total_asset_reconciled": None,
                "authoritative_event_type": False,
                "accounting_verified": False,
                "status": "PARTIAL",
                "reason": (
                    "No authoritative corporate-action table: cash dividend, bonus issue, "
                    "and split cannot be distinguished or fully reconciled"
                ),
            }
        )
    return events


def _select_events(events: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        by_symbol.setdefault(str(event["symbol"]), []).append(event)
    chosen: list[dict[str, Any]] = []
    for symbol in sorted(by_symbol):
        if len(chosen) >= limit:
            break
        chosen.append(sorted(by_symbol[symbol], key=lambda item: item["ex_date"])[-1])
    if len(chosen) < limit:
        chosen_keys = {(row["symbol"], row["ex_date"]) for row in chosen}
        remainder = [
            row
            for row in sorted(events, key=lambda item: (item["ex_date"], item["symbol"]))
            if (row["symbol"], row["ex_date"]) not in chosen_keys
        ]
        chosen.extend(remainder[: limit - len(chosen)])
    return sorted(chosen, key=lambda item: (item["ex_date"], item["symbol"]))


def audit_corporate_actions(connection, symbols: list[str], min_events: int = 20) -> dict[str, Any]:
    if not symbols:
        return {
            "rows": [],
            "evidence": GateEvidence.blocked(
                "No audited symbols were available for corporate-action inspection",
                "corporate_actions.csv",
            ),
        }
    placeholders = ", ".join(["%s"] * len(symbols))
    rows = connection.query(
        "SELECT symbol, tradedate, close, preclose, adjfactor "
        f"FROM bao_a_stock_eod_info WHERE symbol IN ({placeholders}) "
        "AND tradedate BETWEEN %s AND %s ORDER BY symbol, tradedate",
        tuple(symbols) + ("2015-01-01", "2023-06-09"),
    )
    events = _select_events(detect_action_candidates(rows), min_events)
    if len(events) < min_events:
        reason = f"Only {len(events)} of {min_events} required event candidates were available"
        evidence = GateEvidence.blocked(reason, "corporate_actions.csv")
    else:
        evidence = GateEvidence.partial(
            "20+ factor/preclose events inspected, but no authoritative event type or share-change table exists",
            "corporate_actions.csv",
        )
    return {"rows": events, "evidence": evidence}

