from __future__ import annotations

import datetime as dt

import numpy as np

from quantradar.kronos.signal.adapter import (
    SIGNAL_COLUMNS,
    build_signals,
    prediction_content_hash,
)


def _paths() -> np.ndarray:
    values = np.ones((5, 2, 10, 6), dtype=np.float32)
    values[:, :, 0, 0] = 100.0
    # Security B deliberately has the same valid returns as A so symbol is the tie-break.
    closes = [90.0, 100.0, 110.0, 120.0, np.nan]
    for path, close in enumerate(closes):
        values[path, :, -1, 3] = close
    return values


def test_build_signals_calculates_distribution_and_stable_rank():
    predictions = _paths()
    frame = build_signals(
        predictions,
        symbols=["600001.XSHG", "600000.XSHG"],
        signal_run_id="sig_123",
        signal_date=dt.date(2022, 6, 24),
        execution_date=dt.date(2022, 6, 27),
        input_start_date=dt.date(2022, 2, 14),
        input_end_date=dt.date(2022, 6, 24),
        input_hash="input-sha",
        model_version="Kronos-base",
        model_revision="model-rev",
        tokenizer_revision="tokenizer-rev",
        data_commit="dolt-rev",
    )

    assert list(frame.columns) == list(SIGNAL_COLUMNS)
    assert frame["security"].tolist() == ["600000.XSHG", "600001.XSHG"]
    assert frame["rank"].tolist() == [1, 2]
    row = frame.iloc[0]
    assert np.isclose(row["pred_return"], 0.05)
    assert np.isclose(row["q10_return"], -0.07)
    assert np.isclose(row["q50_return"], 0.05)
    assert np.isclose(row["q90_return"], 0.17)
    assert np.isclose(row["up_probability"], 0.5)
    assert np.isclose(row["uncertainty"], np.std([-0.1, 0.0, 0.1, 0.2]))
    assert row["valid_path_count"] == 4
    assert row["invalid_path_count"] == 1
    assert bool(row["eligible"]) is True
    assert row["execution_date"] > row["signal_date"]


def test_all_invalid_paths_remain_auditable_but_ineligible():
    predictions = _paths()
    predictions[:, 1, 0, 0] = 0.0
    frame = build_signals(
        predictions,
        symbols=["600000.XSHG", "600001.XSHG"],
        signal_run_id="sig_123",
        signal_date="2022-06-24",
        execution_date="2022-06-27",
        input_start_date="2022-02-14",
        input_end_date="2022-06-24",
        input_hash="input-sha",
        model_version="Kronos-base",
        model_revision="model-rev",
        tokenizer_revision="tokenizer-rev",
        data_commit="dolt-rev",
    )

    invalid = frame.loc[frame["security"] == "600001.XSHG"].iloc[0]
    assert bool(invalid["eligible"]) is False
    assert invalid["eligibility_status"] == "INVALID_PREDICTION_PATHS"
    assert invalid["exclusion_reason"] == "no valid prediction path"
    assert invalid["valid_path_count"] == 0
    assert invalid["invalid_path_count"] == 5
    assert np.isnan(invalid["rank"])


def test_prediction_hash_covers_symbols_and_values():
    predictions = _paths()
    first = prediction_content_hash(predictions, ["A", "B"])
    assert first == prediction_content_hash(predictions.copy(), ["A", "B"])
    changed = predictions.copy()
    changed[0, 0, -1, 3] = 91.0
    assert first != prediction_content_hash(changed, ["A", "B"])
    assert first != prediction_content_hash(predictions, ["B", "A"])


def test_execution_date_must_follow_signal_date():
    import pytest

    with pytest.raises(ValueError, match="execution_date must be later"):
        build_signals(
            _paths(),
            symbols=["A", "B"],
            signal_run_id="sig",
            signal_date="2022-06-24",
            execution_date="2022-06-24",
            input_start_date="2022-02-14",
            input_end_date="2022-06-24",
            input_hash="input",
            model_version="Kronos-base",
            model_revision="model",
            tokenizer_revision="tokenizer",
            data_commit="dolt",
        )
