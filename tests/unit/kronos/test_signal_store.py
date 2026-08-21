from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from quantradar.kronos.signal.store import (
    ArtifactIntegrityError,
    SignalArtifactStore,
)


CONFIG = {"lookback_days": 90, "prediction_days": 10, "seeds": [101, 211]}
MODEL_LOCK = {"model": {"revision": "model-rev"}, "tokenizer": {"revision": "tok-rev"}}
DATA_CONTRACT = {"price": {"fq": "qfq", "pre_factor_ref_date": "signal_date"}}


def _signals(day: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "signal_date": [pd.Timestamp(day).date()],
            "security": ["600000.XSHG"],
            "pred_return": [0.1],
            "rank": [1.0],
        }
    )


def _create(tmp_path) -> SignalArtifactStore:
    return SignalArtifactStore.create(
        tmp_path,
        config=CONFIG,
        model_lock=MODEL_LOCK,
        data_contract=DATA_CONTRACT,
        data_commit="dolt-rev",
        requested_dates=["2022-06-24", "2022-07-01"],
    )


def test_partition_commit_is_atomic_and_resume_validates_hashes(tmp_path):
    store = _create(tmp_path)
    store.commit_week(
        "2022-06-24",
        signals=_signals("2022-06-24"),
        input_manifest={"input_content_sha256": "input-sha"},
        predictions={"predictions": np.ones((2, 1, 10, 6), dtype=np.float32)},
    )

    week = store.run_dir / "weeks" / "2022-06-24"
    assert (week / "partition_manifest.json").is_file()
    assert not list((store.run_dir / "weeks").glob(".*.tmp"))
    assert store.completed_dates() == ["2022-06-24"]
    reopened = SignalArtifactStore.resume(
        store.run_dir,
        config=CONFIG,
        model_lock=MODEL_LOCK,
        data_contract=DATA_CONTRACT,
        data_commit="dolt-rev",
        requested_dates=["2022-06-24", "2022-07-01"],
    )
    assert reopened.validate_week("2022-06-24")["input_hash"] == "input-sha"


def test_resume_rejects_changed_configuration(tmp_path):
    store = _create(tmp_path)
    changed = dict(CONFIG, prediction_days=5)
    with pytest.raises(ArtifactIntegrityError, match="run fingerprint"):
        SignalArtifactStore.resume(
            store.run_dir,
            config=changed,
            model_lock=MODEL_LOCK,
            data_contract=DATA_CONTRACT,
            data_commit="dolt-rev",
            requested_dates=["2022-06-24", "2022-07-01"],
        )


def test_tampered_partition_is_not_treated_as_complete(tmp_path):
    store = _create(tmp_path)
    store.commit_week(
        "2022-06-24",
        signals=_signals("2022-06-24"),
        input_manifest={"input_content_sha256": "input-sha"},
        predictions={"predictions": np.ones((2, 1, 10, 6), dtype=np.float32)},
    )
    signals_path = store.run_dir / "weeks" / "2022-06-24" / "signals.parquet"
    signals_path.write_bytes(signals_path.read_bytes() + b"tampered")

    with pytest.raises(ArtifactIntegrityError, match="signals.parquet hash mismatch"):
        store.validate_week("2022-06-24")


def test_merge_writes_progress_and_deterministic_root_manifest(tmp_path):
    store = _create(tmp_path)
    for day, value in [("2022-07-01", 0.2), ("2022-06-24", 0.1)]:
        frame = _signals(day)
        frame["pred_return"] = value
        store.commit_week(
            day,
            signals=frame,
            input_manifest={"input_content_sha256": f"input-{day}"},
            predictions={"predictions": np.full((1, 1, 10, 6), value, dtype=np.float32)},
        )
    manifest = store.merge()

    merged = pd.read_parquet(store.run_dir / "signals.parquet")
    assert merged["signal_date"].astype(str).tolist() == ["2022-06-24", "2022-07-01"]
    progress = json.loads((store.run_dir / "progress.json").read_text())
    assert progress == {"completed_dates": ["2022-06-24", "2022-07-01"], "pending_dates": []}
    assert manifest["signal_run_id"] == store.run_id
    assert manifest["formal_backtest_ready"] is False
    assert manifest["real_assist_data_ready"] is False
