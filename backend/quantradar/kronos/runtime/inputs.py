from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from quantradar.audit import dolt_head_commit
from quantradar.providers.investment_data.symbols import normalize_stock_symbol

from .contracts import LOOKBACK_DAYS, PREDICTION_DAYS

FEATURE_NAMES = ("open", "high", "low", "close", "volume", "amount")


@dataclass
class SymbolWindow:
    symbol: str
    values: np.ndarray
    dates: tuple[dt.date, ...]
    listed_trade_days: int
    is_st: bool | None
    tradestatus: bool | None

    @property
    def average_amount_20d(self) -> float:
        return float(np.mean(self.values[-20:, FEATURE_NAMES.index("amount")]))


@dataclass(frozen=True)
class WindowSelection:
    eligible: list[SymbolWindow]
    exclusions: dict[str, str]
    partial_status_symbols: list[str]


def validate_window(window: SymbolWindow) -> str | None:
    values = np.asarray(window.values)
    if values.shape != (LOOKBACK_DAYS, len(FEATURE_NAMES)):
        return f"expected {LOOKBACK_DAYS} complete rows, got {values.shape[0]}"
    if len(window.dates) != LOOKBACK_DAYS:
        return f"expected {LOOKBACK_DAYS} timestamps, got {len(window.dates)}"
    if window.listed_trade_days < 120:
        return "listed for fewer than 120 trading days"
    if not np.isfinite(values).all():
        return "missing or non-finite OHLCVA value"
    open_, high, low, close = (values[:, index] for index in range(4))
    if (
        np.any(low > high)
        or np.any(open_ < low)
        or np.any(open_ > high)
        or np.any(close < low)
        or np.any(close > high)
        or np.any(values[:, 4:] < 0)
    ):
        return "invalid OHLC structure"
    if window.is_st is True:
        return "known ST on signal date"
    if window.tradestatus is False:
        return "known non-trading on signal date"
    return None


def select_eligible_windows(windows: Iterable[SymbolWindow]) -> WindowSelection:
    valid: list[SymbolWindow] = []
    exclusions: dict[str, str] = {}
    for window in sorted(windows, key=lambda item: item.symbol):
        reason = validate_window(window)
        if reason:
            exclusions[window.symbol] = reason
        else:
            valid.append(window)

    keep_count = math.ceil(len(valid) * 0.8)
    liquid = sorted(valid, key=lambda item: (-item.average_amount_20d, item.symbol))[
        :keep_count
    ]
    kept_symbols = {item.symbol for item in liquid}
    for item in valid:
        if item.symbol not in kept_symbols:
            exclusions[item.symbol] = "bottom 20 percent by 20-day amount"
    eligible = sorted(liquid, key=lambda item: item.symbol)
    partial = [
        item.symbol
        for item in eligible
        if item.is_st is None or item.tradestatus is None
    ]
    return WindowSelection(eligible, dict(sorted(exclusions.items())), partial)


def _hash_bytes(digest: Any, value: bytes) -> None:
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def array_content_hash(arrays: dict[str, np.ndarray]) -> str:
    digest = hashlib.sha256()
    for name in sorted(arrays):
        value = np.ascontiguousarray(arrays[name])
        _hash_bytes(digest, name.encode("utf-8"))
        _hash_bytes(digest, value.dtype.str.encode("ascii"))
        _hash_bytes(digest, json.dumps(value.shape).encode("ascii"))
        _hash_bytes(digest, value.tobytes())
    return digest.hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _date_array(values: Iterable[dt.date]) -> np.ndarray:
    return np.asarray([value.isoformat() for value in values], dtype="U10")


def publish_input_package(
    *,
    output_dir: str | Path,
    selection: WindowSelection,
    signal_date: dt.date,
    future_dates: list[dt.date],
    pit_snapshot_date: dt.date,
    data_commit: str,
    data_contract_hash: str,
    available_pit_signal_weeks: int | None = None,
) -> dict[str, Any]:
    if len(future_dates) != PREDICTION_DAYS:
        raise ValueError(f"Expected {PREDICTION_DAYS} future trading dates")
    if len(selection.eligible) < 50:
        raise ValueError("Goal 1 requires at least 50 eligible PIT symbols")

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    arrays = {
        "values": np.stack([item.values for item in selection.eligible]).astype(
            np.float32
        ),
        "symbols": np.asarray(
            [item.symbol for item in selection.eligible], dtype="U16"
        ),
        "x_dates": np.stack([_date_array(item.dates) for item in selection.eligible]),
        "y_dates": _date_array(future_dates),
    }
    npz_path = output / "runtime_inputs.npz"
    npz_temp = output / ".runtime_inputs.npz.tmp"
    with npz_temp.open("wb") as handle:
        np.savez_compressed(handle, **arrays)
    os.replace(npz_temp, npz_path)

    manifest = {
        "version": "kronos-runtime-input-v1",
        "signal_date": signal_date.isoformat(),
        "pit_snapshot_date": pit_snapshot_date.isoformat(),
        "lookback_days": LOOKBACK_DAYS,
        "prediction_days": PREDICTION_DAYS,
        "feature_names": list(FEATURE_NAMES),
        "eligible_symbol_count": len(selection.eligible),
        "eligible_symbols": [item.symbol for item in selection.eligible],
        "excluded_symbol_count": len(selection.exclusions),
        "exclusions": selection.exclusions,
        "tradeability_status": (
            "PARTIAL" if selection.partial_status_symbols else "PASS"
        ),
        "partial_status_symbols": selection.partial_status_symbols,
        "data_commit": data_commit,
        "data_contract_sha256": data_contract_hash,
        "available_pit_signal_weeks": available_pit_signal_weeks,
        "input_content_sha256": array_content_hash(arrays),
        "npz_sha256": sha256_file(npz_path),
    }
    manifest_path = output / "input_manifest.json"
    manifest_temp = output / ".input_manifest.json.tmp"
    manifest_temp.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(manifest_temp, manifest_path)
    return manifest


def _status_value(raw: Any, *, is_st: bool) -> bool | None:
    if raw is None:
        return None
    try:
        numeric = int(raw)
    except (TypeError, ValueError):
        return None
    return bool(numeric) if is_st else numeric == 1


def _collect_status(
    connection, symbols: list[str], signal_date: dt.date
) -> dict[str, tuple[bool | None, bool | None]]:
    if not symbols:
        return {}
    internal_to_jq = {normalize_stock_symbol(symbol): symbol for symbol in symbols}
    placeholders = ",".join(["%s"] * len(internal_to_jq))
    rows = connection.query(
        "SELECT symbol, is_st, tradestatus FROM bao_a_stock_eod_info "
        f"WHERE tradedate = %s AND symbol IN ({placeholders})",
        (signal_date.isoformat(), *internal_to_jq),
    )
    result = {symbol: (None, None) for symbol in symbols}
    for row in rows:
        jq_symbol = internal_to_jq.get(row["symbol"])
        if jq_symbol:
            result[jq_symbol] = (
                _status_value(row.get("is_st"), is_st=True),
                _status_value(row.get("tradestatus"), is_st=False),
            )
    return result


def collect_real_input_package(
    provider,
    *,
    output_dir: str | Path,
    data_contract_path: str | Path,
) -> dict[str, Any]:
    connection = provider.connection
    start_commit = dolt_head_commit(connection)
    snapshot = connection.query_one(
        "SELECT MIN(trade_date) AS first_snapshot_date, "
        "MAX(trade_date) AS snapshot_date FROM ts_index_weight "
        "WHERE index_code = %s",
        ("000300.SH",),
    ) or {}
    signal_date = snapshot.get("snapshot_date")
    first_snapshot_date = snapshot.get("first_snapshot_date")
    if not isinstance(signal_date, dt.date):
        raise RuntimeError("No real 000300.SH PIT snapshot is available")

    symbols = sorted(provider.get_index_stocks("000300.XSHG", date=signal_date))
    statuses = _collect_status(connection, symbols, signal_date)
    securities = provider.get_all_securities("stock", date=signal_date)
    open_days = [item.date() for item in provider.get_trade_days(end_date=signal_date)]
    available_pit_signal_weeks = None
    if isinstance(first_snapshot_date, dt.date):
        available_pit_signal_weeks = len(
            {
                (day.isocalendar().year, day.isocalendar().week)
                for day in open_days
                if first_snapshot_date <= day <= signal_date
            }
        )
    future_dates = [
        item.date()
        for item in provider.get_trade_days(
            start_date=signal_date + dt.timedelta(days=1), count=PREDICTION_DAYS
        )
    ]

    windows: list[SymbolWindow] = []
    for symbol in symbols:
        frame = provider.get_price(
            symbol,
            end_date=signal_date,
            count=LOOKBACK_DAYS,
            fields=list(FEATURE_NAMES),
            fq="qfq",
            pre_factor_ref_date=signal_date,
            fill_paused=False,
        )
        start_date = None
        if symbol in securities.index:
            raw_start = securities.loc[symbol, "start_date"]
            if not pd.isna(raw_start):
                start_date = pd.Timestamp(raw_start).date()
        listed_days = (
            sum(day >= start_date for day in open_days)
            if start_date is not None
            else 0
        )
        is_st, tradestatus = statuses.get(symbol, (None, None))
        windows.append(
            SymbolWindow(
                symbol=symbol,
                values=frame.loc[:, list(FEATURE_NAMES)].to_numpy(dtype=np.float64),
                dates=tuple(index.date() for index in frame.index),
                listed_trade_days=listed_days,
                is_st=is_st,
                tradestatus=tradestatus,
            )
        )

    selection = select_eligible_windows(windows)
    end_commit = dolt_head_commit(connection)
    if not start_commit or start_commit != end_commit:
        raise RuntimeError(
            f"Dolt HEAD changed while building runtime input: {start_commit} -> {end_commit}"
        )
    return publish_input_package(
        output_dir=output_dir,
        selection=selection,
        signal_date=signal_date,
        future_dates=future_dates,
        pit_snapshot_date=signal_date,
        data_commit=start_commit,
        data_contract_hash=sha256_file(data_contract_path),
        available_pit_signal_weeks=available_pit_signal_weeks,
    )
