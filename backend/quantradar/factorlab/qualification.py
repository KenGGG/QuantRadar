"""Data qualification for independent Alpha101 batch items."""
from __future__ import annotations


def preflight(available_fields: set[str], required_fields: set[str]) -> dict[str, object]:
    """Return a data outcome; missing research facts are never engine errors."""
    missing = sorted(required_fields - available_fields)
    return {"status": "BLOCKED_INPUT" if missing else "READY", "missing_fields": missing}


def batch_status(item_statuses: list[str]) -> str:
    """Summarize independent item outcomes without discarding completed work."""
    if any(status == "FAILED_ENGINE" for status in item_statuses):
        return "FAILED"
    completed = {"COMPUTED", "FORMULA_EMPTY_VALID", "CACHE_HIT"}
    if any(status in completed for status in item_statuses):
        return "SUCCESS" if all(status in completed for status in item_statuses) else "PARTIAL_SUCCESS"
    return "BLOCKED"
