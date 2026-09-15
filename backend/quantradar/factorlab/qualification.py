"""Data qualification for independent Alpha101 batch items."""
from __future__ import annotations

import pandas as pd


def qualified_industry_fields(manifest: dict[str, object]) -> set[str]:
    """Expose hierarchy inputs only when their fixed release has a dictionary."""
    metadata = manifest.get("metadata") if isinstance(manifest, dict) else None
    hierarchy = metadata.get("sw_industry_hierarchy") if isinstance(metadata, dict) else None
    if not isinstance(hierarchy, dict) or not hierarchy.get("dictionary_version"):
        return set()
    if hierarchy.get("levels") != ["L1", "L2", "L3"]:
        return set()
    # A six-digit assignment alone does not prove that its prefixes map to
    # documented SW hierarchy levels.  The published dictionary must attest
    # that relation before either the Provider or FactorLab derives levels.
    if hierarchy.get("code_hierarchy") != "PREFIX_VERIFIED_BY_DICTIONARY":
        return set()
    return {"indclass.sector", "indclass.industry", "indclass.subindustry"}


def preflight(available_fields: set[str], required_fields: set[str], *,
              panel_dates: pd.DatetimeIndex | None = None,
              requested_dates: pd.DatetimeIndex | None = None,
              lookback_days: int | None = None, panel: dict[str, pd.DataFrame] | None = None) -> dict[str, object]:
    """Return a data outcome; missing research facts are never engine errors."""
    missing = sorted(required_fields - available_fields)
    if missing:
        return {"status": "BLOCKED_INPUT", "missing_fields": missing}
    if panel is not None:
        universe = panel.get("universe")
        if universe is not None and not universe.fillna(False).astype(bool).any().any():
            return {"status": "BLOCKED_INPUT", "missing_fields": ["universe"], "reason": "no effective observations"}
        # A field existing somewhere in the panel does not prove that the
        # formula has one computable security/date.  Intersect every required
        # input with the explicit lifecycle universe before allowing the
        # engine to classify an all-NaN result as mathematical.
        if universe is not None:
            eligible = universe.fillna(False).astype(bool)
            individually_empty: list[str] = []
            for field in sorted(required_fields):
                frame = panel.get(field)
                if frame is None:
                    continue
                valid = frame.notna().reindex(index=eligible.index, columns=eligible.columns, fill_value=False)
                if not (universe.fillna(False).astype(bool) & valid).any().any():
                    individually_empty.append(field)
                eligible &= valid
            if individually_empty:
                return {"status": "BLOCKED_INPUT", "missing_fields": individually_empty,
                        "reason": "no effective observations"}
            if not eligible.any().any():
                return {"status": "BLOCKED_INPUT", "missing_fields": sorted(required_fields),
                        "reason": "no jointly eligible observations"}
        else:
            empty = sorted(field for field in required_fields if field in panel and not panel[field].notna().any().any())
            if empty:
                return {"status": "BLOCKED_INPUT", "missing_fields": empty, "reason": "no effective observations"}
    if panel_dates is not None and requested_dates is not None and lookback_days:
        if len(requested_dates) == 0:
            return {"status": "BLOCKED_WARMUP", "missing_fields": [],
                    "warmup_available": 0, "warmup_required": lookback_days}
        first = pd.Timestamp(requested_dates[0])
        available = int(panel_dates.searchsorted(first, side="right"))
        if available < lookback_days:
            return {"status": "BLOCKED_WARMUP", "missing_fields": [],
                    "warmup_available": available, "warmup_required": lookback_days}
    return {"status": "READY", "missing_fields": []}


def batch_status(item_statuses: list[str]) -> str:
    """Summarize independent item outcomes without discarding completed work."""
    if any(status == "FAILED_ENGINE" for status in item_statuses):
        return "FAILED"
    completed = {"COMPUTED", "FORMULA_EMPTY_VALID", "CACHE_HIT"}
    if any(status in completed for status in item_statuses):
        return "SUCCESS" if all(status in completed for status in item_statuses) else "PARTIAL_SUCCESS"
    return "BLOCKED"
