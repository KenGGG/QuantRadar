"""A small reproducibility probe that genuinely reads both repositories in one release."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .reader import ReleaseReader


def _base_symbol(symbol: str) -> str:
    code, exchange = symbol.upper().split(".", 1)
    if len(code) != 6 or exchange not in {"SH", "SZ"}:
        raise ValueError(f"unsupported DataHub symbol: {symbol}")
    return exchange + code


def run_research_sample(reader: ReleaseReader, *, release_id: str, symbol: str, as_of: str) -> dict[str, Any]:
    """Read base price/status plus all three supplemental V1 domains at fixed commits."""
    scope = reader.resolve(release_id)
    base = reader.base_connection(scope)
    price = base.query_one(
        "SELECT p.symbol, p.tradedate, p.close, i.turn, i.is_st, i.tradestatus "
        "FROM final_a_stock_eod_price p LEFT JOIN bao_a_stock_eod_info i "
        "ON p.symbol=i.symbol AND p.tradedate=i.tradedate "
        "WHERE p.symbol=%s AND p.tradedate=%s",
        (_base_symbol(symbol), as_of),
    )
    if price is None:
        raise ValueError(f"base price/status missing for {symbol} at {as_of}")
    supplemental = reader.supplemental_reader(scope)
    valuation = supplemental.valuation(symbol, as_of, as_of, required_fields=("pe_ttm", "pb_mrq", "ps_ttm", "pcf_ocf_ttm"))
    if not valuation["rows"]:
        raise ValueError(f"supplemental valuation missing for {symbol} at {as_of}")
    industry = supplemental.industry_as_of(symbol, as_of)
    lifecycle = supplemental.lifecycle_as_of(symbol, as_of)
    if industry is None or lifecycle is None:
        raise ValueError(f"supplemental industry/lifecycle missing for {symbol} at {as_of}")
    output = {
        "release_id": scope.release_id,
        "base_commit": scope.manifest["base_commit"],
        "supplemental_commit": scope.manifest["supplemental_commit"],
        "symbol": symbol,
        "as_of": as_of,
        "base": price,
        "valuation": valuation["rows"][0],
        "industry": industry,
        "lifecycle": lifecycle,
    }
    payload = json.dumps(output, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
    output["result_hash"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return output
