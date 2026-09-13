"""Field-level checks for controlled A-share daily candidates."""
from __future__ import annotations

from typing import Any, Iterable


def reconcile_stock_sample(candidate: Iterable[dict[str, Any]], reference: Iterable[dict[str, Any]], *, tolerance: float = 1e-6) -> dict[str, Any]:
    """Verify BaoStock shares/yuan against frozen hand/thousand-yuan reference."""
    candidate_by_key = {(str(row["symbol"]), str(row["trade_date"])): row for row in candidate}
    reference_by_key = {(str(row["symbol"]), str(row["trade_date"])): row for row in reference}
    if not candidate_by_key or set(candidate_by_key) != set(reference_by_key):
        raise ValueError("candidate/reference date-security keys differ")
    checks = {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume_shares": 100.0, "amount_cny": 1000.0}
    reference_field = {"volume_shares": "volume", "amount_cny": "amount"}
    # Frozen base values are displayed to 0.01 hand and 0.001 thousand yuan.
    # These are display-rounding bounds, not permission to rescale a source.
    display_rounding = {"volume_shares": 50.0, "amount_cny": 1.0}
    differences: list[dict[str, Any]] = []
    for key, actual in candidate_by_key.items():
        expected = reference_by_key[key]
        for field, multiplier in checks.items():
            baseline = float(expected[reference_field.get(field, field)]) * multiplier
            observed = float(actual[field])
            allowed = max(tolerance * max(1.0, abs(baseline)), display_rounding.get(field, 0.0))
            if abs(observed - baseline) > allowed:
                differences.append({"symbol": key[0], "trade_date": key[1], "field": field, "candidate": observed, "reference": baseline})
    return {
        "status": "PASS" if not differences else "FAIL",
        "rows": len(candidate_by_key),
        "unit_contract": "baostock-shares-yuan",
        "reference_contract": "base-hands-thousand-yuan",
        "differences": differences,
    }
