"""Conservative mappings from immutable financial source versions."""
from __future__ import annotations

import hashlib


def conservative_available_at(announcement_date: str | None, precision: str, trade_days: list[str]) -> tuple[str | None, str | None]:
    """Derive a research rule without changing the source announcement fact."""
    if not announcement_date or precision != "DATE_ONLY":
        return None, None
    later = next((day for day in trade_days if day > announcement_date[:10]), None)
    if later is None:
        return None, "CN_DATE_ONLY_NEXT_TRADING_SESSION_V1"
    return later + "T09:30:00+08:00", "CN_DATE_ONLY_NEXT_TRADING_SESSION_V1"


_FIELDS = {
    "balance": {"total_assets": "TOTAL_ASSETS", "total_liabilities": "TOTAL_LIABILITIES", "total_equity": "TOTAL_EQUITY",
                "cash": "MONETARYFUNDS", "accounts_receivable": "ACCOUNTS_RECE", "inventory": "INVENTORY",
                "short_term_debt": "SHORT_LOAN", "long_term_debt": "LONG_LOAN"},
    "income": {"operating_revenue": "TOTAL_OPERATE_INCOME", "operating_profit": "OPERATE_PROFIT", "total_profit": "TOTAL_PROFIT",
               "net_profit": "NETPROFIT", "net_profit_parent": "PARENT_NETPROFIT"},
    "cashflow": {"operating_cash_flow": "NETCASH_OPERATE", "investing_cash_flow": "NETCASH_INVEST",
                 "financing_cash_flow": "NETCASH_FINANCE", "cash_change": "CCE_ADD", "capex": "CONSTRUCT_LONG_ASSET"},
}


def map_statement_row(statement_type: str, raw: dict) -> dict[str, float | None]:
    if statement_type not in _FIELDS:
        raise ValueError("unsupported statement type")
    def number(value):
        return None if value is None else float(value)
    return {target: number(raw.get(source)) for target, source in _FIELDS[statement_type].items()}


def statement_version_id(symbol: str, statement_type: str, report_period: str, raw_sha256: str) -> str:
    """A supplier record identity changes only when its immutable receipt changes."""
    value = "|".join((symbol, statement_type, report_period, raw_sha256))
    return "sv_" + hashlib.sha256(value.encode()).hexdigest()[:40]
