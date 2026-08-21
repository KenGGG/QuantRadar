from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Any

import pandas as pd

from quantradar.providers.investment_data.symbols import (
    normalize_stock_symbol,
    to_joinquant_symbol,
)

from .models import GateEvidence


_OHLC = ("open", "high", "low", "close")


def _board(symbol: str) -> str:
    if symbol.startswith("SH688"):
        return "STAR"
    if symbol.startswith("SH6"):
        return "SH_MAIN"
    if symbol.startswith("SZ30"):
        return "CHINEXT"
    return "SZ_MAIN"


def _category(symbol: str, avg_close: float) -> tuple[str, str]:
    board = _board(symbol)
    price = "LOW" if avg_close < 10 else "MID" if avg_close < 100 else "HIGH"
    return board, price


def select_board_pool(symbols: list[str], per_board: int = 20) -> list[str]:
    by_board: dict[str, list[str]] = defaultdict(list)
    for symbol in sorted(set(symbols)):
        by_board[_board(symbol)].append(symbol)
    selected = [
        symbol
        for board in sorted(by_board)
        for symbol in by_board[board][:per_board]
    ]
    return sorted(selected)


def select_diverse_symbols(candidates: list[dict[str, Any]], limit: int = 30) -> list[str]:
    """Deterministically round-robin board/price buckets, then return stable symbols."""
    buckets: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in sorted(candidates, key=lambda item: str(item["symbol"])):
        buckets[_category(str(row["symbol"]), float(row["avg_close"]))].append(
            str(row["symbol"])
        )
    selected: list[str] = []
    keys = sorted(buckets)
    while len(selected) < limit and any(buckets.values()):
        for key in keys:
            if buckets[key] and len(selected) < limit:
                selected.append(buckets[key].pop(0))
    return sorted(selected)


def expected_adjusted_prices(
    raw: pd.DataFrame,
    mode: str,
    *,
    reference_date: dt.date | None = None,
) -> pd.DataFrame:
    if raw.empty:
        return raw.copy()
    close = raw["close"].astype(float)
    if close.isna().any() or (close <= 0).any():
        raise ValueError("positive close is required to derive adjustment factors")
    factor = raw["adjclose"].astype(float) / close
    if factor.isna().any() or (factor <= 0).any():
        raise ValueError("positive adjustment factor is required")
    if mode in {"hfq", "post"}:
        scale = factor
    elif mode in {"qfq", "pre"}:
        if reference_date is None:
            raise ValueError("qfq requires an explicit reference_date")
        matches = raw.index[pd.to_datetime(raw.index).date == reference_date]
        if len(matches) != 1:
            raise ValueError("reference_date must identify exactly one input row")
        reference_factor = float(factor.loc[matches[0]])
        scale = factor / reference_factor
    else:
        raise ValueError(f"unsupported adjustment mode: {mode}")
    result = raw.copy()
    for field in _OHLC:
        result[field] = raw[field].astype(float) * scale
    return result


def _max_abs_error(left: pd.Series, right: pd.Series) -> float:
    return float((left.astype(float) - right.astype(float)).abs().max())


def audit_price_semantics(connection, provider, min_samples: int = 30) -> dict[str, Any]:
    constituent_rows = connection.query(
        "SELECT DISTINCT stock_code FROM ts_index_weight "
        "WHERE index_code = %s ORDER BY stock_code",
        ("000300.SH",),
    )
    pool = select_board_pool(
        [normalize_stock_symbol(row["stock_code"]) for row in constituent_rows],
        per_board=20,
    )
    candidates: list[dict[str, Any]] = []
    raw_by_symbol: dict[str, pd.DataFrame] = {}
    for symbol in pool:
        rows = connection.query(
            "SELECT tradedate, open, high, low, close, adjclose, volume, amount "
            "FROM final_a_stock_eod_price WHERE symbol = %s AND close > 0 "
            "AND adjclose > 0 AND tradedate <= %s ORDER BY tradedate DESC LIMIT 120",
            (symbol, "2023-06-09"),
        )
        rows.reverse()
        raw = pd.DataFrame(rows)
        if len(raw) < 120:
            continue
        raw.index = pd.to_datetime(raw.pop("tradedate"))
        factor = raw["adjclose"].astype(float) / raw["close"].astype(float)
        candidates.append(
            {
                "symbol": symbol,
                "avg_close": float(raw["close"].mean()),
                "min_date": raw.index[0].date(),
                "max_date": raw.index[-1].date(),
                "min_factor": float(factor.min()),
                "max_factor": float(factor.max()),
                "zero_volume_days": int((raw["volume"].fillna(0) == 0).sum()),
            }
        )
        raw_by_symbol[symbol] = raw
    symbols = select_diverse_symbols(candidates, min_samples)
    candidate_by_symbol = {str(row["symbol"]): row for row in candidates}
    results: list[dict[str, Any]] = []
    for symbol in symbols:
        raw = raw_by_symbol[symbol]
        start = raw.index[0].date()
        end = raw.index[-1].date()
        jq_symbol = to_joinquant_symbol(symbol)
        provider_raw = provider.get_price(jq_symbol, start, end, fq="none")
        provider_hfq = provider.get_price(jq_symbol, start, end, fq="hfq")
        provider_qfq = provider.get_price(
            jq_symbol, start, end, fq="qfq", pre_factor_ref_date=end
        )
        expected_hfq = expected_adjusted_prices(raw, "hfq")
        expected_qfq = expected_adjusted_prices(raw, "qfq", reference_date=end)
        common = raw.index.intersection(provider_raw.index)
        meta = candidate_by_symbol[symbol]
        result = {
            "symbol": jq_symbol,
            "internal_symbol": symbol,
            "board": _category(symbol, float(meta["avg_close"]))[0],
            "price_bucket": _category(symbol, float(meta["avg_close"]))[1],
            "input_start_date": start,
            "input_end_date": end,
            "input_rows": len(common),
            "factor_changed": float(meta["max_factor"]) > float(meta["min_factor"]),
            "has_zero_volume_history": int(meta["zero_volume_days"] or 0) > 0,
        }
        for field in _OHLC:
            result[f"none_{field}_max_abs_error"] = _max_abs_error(
                provider_raw.loc[common, field], raw.loc[common, field]
            )
            result[f"hfq_{field}_max_abs_error"] = _max_abs_error(
                provider_hfq.loc[common, field], expected_hfq.loc[common, field]
            )
            result[f"qfq_{field}_max_abs_error"] = _max_abs_error(
                provider_qfq.loc[common, field], expected_qfq.loc[common, field]
            )
        result["hfq_close_vs_adjclose_max_abs_error"] = _max_abs_error(
            provider_hfq.loc[common, "close"], raw.loc[common, "adjclose"]
        )
        result["volume_unchanged"] = _max_abs_error(
            provider_qfq.loc[common, "volume"], raw.loc[common, "volume"]
        ) == 0.0
        result["amount_unchanged"] = _max_abs_error(
            provider_qfq.loc[common, "amount"], raw.loc[common, "amount"]
        ) == 0.0
        numeric_errors = [
            value for key, value in result.items() if key.endswith("_max_abs_error")
        ]
        result["status"] = (
            "PASS"
            if len(common) == len(raw)
            and max(numeric_errors, default=float("inf")) <= 1e-6
            and result["volume_unchanged"]
            and result["amount_unchanged"]
            else "FAIL"
        )
        results.append(result)

    failed = [row for row in results if row["status"] != "PASS"]
    if len(results) < min_samples:
        gate = GateEvidence.blocked(
            f"Only {len(results)} of {min_samples} required price samples were available",
            "price_semantics.csv",
        )
    elif failed:
        gate = GateEvidence.fail(
            f"{len(failed)} price samples failed raw/fq reconciliation",
            "price_semantics.csv",
        )
    else:
        gate = GateEvidence.pass_("price_semantics.csv", "price_semantics.md")
    contract = {
        "raw_price": "final_a_stock_eod_price.open/high/low/close",
        "adjustment_factor": "final_a_stock_eod_price.adjclose / close",
        "hfq_post": "raw_ohlc * adjustment_factor",
        "qfq_pre": "raw_ohlc * adjustment_factor / factor_at_explicit_reference_date",
        "volume": "final_a_stock_eod_price.volume; unchanged by price adjustment",
        "amount": "final_a_stock_eod_price.amount; unchanged by price adjustment",
        "pre_factor_ref_date": "required for Kronos inputs; signal_date in later goals",
    }
    return {"rows": results, "contract": contract, "evidence": gate}
