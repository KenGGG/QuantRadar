from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Iterable

import numpy as np
import pandas as pd

SIGNAL_COLUMNS = (
    "signal_run_id",
    "signal_date",
    "execution_date",
    "security",
    "prediction_horizon",
    "pred_return",
    "q10_return",
    "q50_return",
    "q90_return",
    "up_probability",
    "uncertainty",
    "rank",
    "eligible",
    "eligibility_status",
    "exclusion_reason",
    "input_start_date",
    "input_end_date",
    "input_rows",
    "input_hash",
    "valid_path_count",
    "invalid_path_count",
    "model_version",
    "model_revision",
    "tokenizer_revision",
    "data_commit",
    "prediction_hash",
)


def _date(value: dt.date | str) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(value)


def _hash_part(digest: object, payload: bytes) -> None:
    digest.update(len(payload).to_bytes(8, "big"))
    digest.update(payload)


def prediction_content_hash(
    predictions: np.ndarray, symbols: Iterable[str]
) -> str:
    values = np.ascontiguousarray(np.asarray(predictions, dtype=np.float32))
    symbol_values = tuple(str(symbol) for symbol in symbols)
    digest = hashlib.sha256()
    _hash_part(digest, json.dumps(symbol_values).encode("utf-8"))
    _hash_part(digest, values.dtype.str.encode("ascii"))
    _hash_part(digest, json.dumps(values.shape).encode("ascii"))
    _hash_part(digest, values.tobytes())
    return digest.hexdigest()


def build_signals(
    predictions: np.ndarray,
    *,
    symbols: Iterable[str],
    signal_run_id: str,
    signal_date: dt.date | str,
    execution_date: dt.date | str,
    input_start_date: dt.date | str,
    input_end_date: dt.date | str,
    input_hash: str,
    model_version: str,
    model_revision: str,
    tokenizer_revision: str,
    data_commit: str,
) -> pd.DataFrame:
    values = np.asarray(predictions, dtype=np.float32)
    symbol_values = [str(symbol) for symbol in symbols]
    if values.ndim != 4 or values.shape[1] != len(symbol_values):
        raise ValueError(
            "predictions must have shape [paths, symbols, horizon, features]"
        )
    if values.shape[2] < 1 or values.shape[3] < 4:
        raise ValueError("predictions require a non-empty horizon and OHLC features")
    signal_day = _date(signal_date)
    execution_day = _date(execution_date)
    if execution_day <= signal_day:
        raise ValueError("execution_date must be later than signal_date")

    prediction_hash = prediction_content_hash(values, symbol_values)
    rows: list[dict[str, object]] = []
    for index, security in enumerate(symbol_values):
        opens = values[:, index, 0, 0].astype(np.float64)
        closes = values[:, index, -1, 3].astype(np.float64)
        valid = np.isfinite(opens) & np.isfinite(closes) & (opens > 0) & (closes > 0)
        returns = closes[valid] / opens[valid] - 1.0
        valid_count = int(valid.sum())
        invalid_count = int(len(valid) - valid_count)
        eligible = valid_count > 0
        if eligible:
            q10, q50, q90 = np.quantile(returns, [0.1, 0.5, 0.9])
            pred_return = float(q50)
            status = "ELIGIBLE"
            reason = None
        else:
            q10 = q50 = q90 = pred_return = np.nan
            status = "INVALID_PREDICTION_PATHS"
            reason = "no valid prediction path"
        rows.append(
            {
                "signal_run_id": signal_run_id,
                "signal_date": signal_day,
                "execution_date": execution_day,
                "security": security,
                "prediction_horizon": int(values.shape[2]),
                "pred_return": pred_return,
                "q10_return": float(q10),
                "q50_return": float(q50),
                "q90_return": float(q90),
                "up_probability": float(np.mean(returns > 0)) if eligible else np.nan,
                "uncertainty": float(np.std(returns)) if eligible else np.nan,
                "rank": np.nan,
                "eligible": eligible,
                "eligibility_status": status,
                "exclusion_reason": reason,
                "input_start_date": _date(input_start_date),
                "input_end_date": _date(input_end_date),
                "input_rows": 90,
                "input_hash": input_hash,
                "valid_path_count": valid_count,
                "invalid_path_count": invalid_count,
                "model_version": model_version,
                "model_revision": model_revision,
                "tokenizer_revision": tokenizer_revision,
                "data_commit": data_commit,
                "prediction_hash": prediction_hash,
            }
        )

    frame = pd.DataFrame(rows, columns=SIGNAL_COLUMNS)
    valid_frame = frame[frame["eligible"]].sort_values(
        ["pred_return", "security"], ascending=[False, True], kind="mergesort"
    )
    frame.loc[valid_frame.index, "rank"] = np.arange(1, len(valid_frame) + 1)
    return frame.sort_values(
        ["eligible", "rank", "security"],
        ascending=[False, True, True],
        kind="mergesort",
        na_position="last",
    ).reset_index(drop=True)
