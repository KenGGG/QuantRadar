from __future__ import annotations

import numpy as np
import pandas as pd

from quantradar.kronos.signal.manifest import content_hash

STRATEGY_VERSION = "kronos_topk_equal_weight_v1"
TARGET_WEIGHT_COLUMNS = (
    "strategy_version",
    "signal_run_id",
    "signal_date",
    "execution_date",
    "security",
    "rank",
    "target_weight",
    "reason",
    "signal_hash",
)


def build_topk_target_weights(signals: pd.DataFrame, topk: int = 20) -> pd.DataFrame:
    if topk <= 0:
        raise ValueError("topk must be positive")
    if signals is None or signals.empty:
        return pd.DataFrame(columns=TARGET_WEIGHT_COLUMNS)
    frame = signals.copy()
    frame["signal_date"] = pd.to_datetime(frame["signal_date"])
    frame["execution_date"] = pd.to_datetime(frame["execution_date"])
    if (frame["execution_date"] <= frame["signal_date"]).any():
        raise ValueError("execution_date must be strictly later than signal_date")
    frame = frame[frame["eligible"].astype(bool) & frame["pred_return"].notna()]
    rows: list[dict] = []
    for execution_date, group in frame.groupby("execution_date", sort=True):
        selected = group.sort_values(
            ["pred_return", "security"],
            ascending=[False, True],
            kind="mergesort",
        ).head(topk)
        if selected.empty:
            continue
        weight = 1.0 / len(selected)
        for rank, (_, item) in enumerate(selected.iterrows(), start=1):
            rows.append(
                {
                    "strategy_version": STRATEGY_VERSION,
                    "signal_run_id": item["signal_run_id"],
                    "signal_date": item["signal_date"].date(),
                    "execution_date": execution_date.date(),
                    "security": item["security"],
                    "rank": rank,
                    "target_weight": weight,
                    "reason": f"top_{len(selected)}_pred_return",
                    "signal_hash": item.get("prediction_hash"),
                }
            )
    return pd.DataFrame(rows, columns=TARGET_WEIGHT_COLUMNS)


def to_wide_weights(weights: pd.DataFrame) -> pd.DataFrame:
    if weights is None or weights.empty:
        return pd.DataFrame()
    wide = (
        weights.pivot(
            index="execution_date", columns="security", values="target_weight"
        )
        .fillna(0.0)
        .sort_index()
        .sort_index(axis=1)
    )
    wide.index = pd.DatetimeIndex(pd.to_datetime(wide.index), name="execution_date")
    return wide


def target_weight_hash(weights: pd.DataFrame) -> str:
    if weights is None:
        raise ValueError("weights must not be None")
    frame = weights.copy()
    for name in ("signal_date", "execution_date"):
        if name in frame:
            frame[name] = pd.to_datetime(frame[name]).dt.strftime("%Y-%m-%d")
    frame = frame.replace({np.nan: None}).sort_values(
        [name for name in ("execution_date", "rank", "security") if name in frame],
        kind="mergesort",
    )
    return content_hash(frame.to_dict(orient="records"))
