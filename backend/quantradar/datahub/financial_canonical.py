"""Conservative mappings from immutable financial source versions."""
from __future__ import annotations


def conservative_available_at(announcement_date: str | None, precision: str, trade_days: list[str]) -> tuple[str | None, str | None]:
    """Derive a research rule without changing the source announcement fact."""
    if not announcement_date or precision != "DATE_ONLY":
        return None, None
    later = next((day for day in trade_days if day > announcement_date[:10]), None)
    if later is None:
        return None, "CN_DATE_ONLY_NEXT_TRADING_SESSION_V1"
    return later + "T09:30:00+08:00", "CN_DATE_ONLY_NEXT_TRADING_SESSION_V1"
