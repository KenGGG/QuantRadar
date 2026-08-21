from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest

from quantradar.kronos.signal.subprocess_runner import (
    SignalSubprocessError,
    build_signal_command,
    run_signal_subprocess,
)
from quantradar.kronos.runtime.inputs import array_content_hash, sha256_file
from kronos_runtime.signal_runner import publish_prediction_artifacts


def test_signal_command_uses_isolated_runtime_and_dedicated_runner(tmp_path):
    command = build_signal_command(
        repo_root=tmp_path,
        input_dir=tmp_path / "input",
        output_dir=tmp_path / "output",
        initial_batch_size=32,
    )
    assert command[0] == str(tmp_path / ".venv-kronos/bin/python")
    assert command[1] == str(tmp_path / "kronos_runtime/signal_runner.py")
    assert command[-2:] == ["--initial-batch-size", "32"]


def test_signal_subprocess_validates_prediction_file_and_content_hash(tmp_path):
    output = tmp_path / "output"

    def fake_run(command, **kwargs):
        output.mkdir(parents=True)
        values = np.ones((5, 2, 10, 6), dtype=np.float32)
        symbols = np.asarray(["A", "B"])
        with (output / "predictions.npz").open("wb") as handle:
            np.savez_compressed(handle, predictions=values, symbols=symbols)
        result = {
            "prediction_content_sha256": array_content_hash(
                {"predictions": values, "symbols": symbols}
            ),
            "predictions_npz_sha256": sha256_file(output / "predictions.npz"),
            "path_count": 5,
            "symbol_count": 2,
        }
        (output / "runtime_result.json").write_text(json.dumps(result))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    result = run_signal_subprocess(
        repo_root=tmp_path,
        input_dir=tmp_path / "input",
        output_dir=output,
        run=fake_run,
    )
    assert result["predictions"].shape == (5, 2, 10, 6)
    assert result["runtime"]["path_count"] == 5


def test_signal_subprocess_rejects_tampered_hash(tmp_path):
    output = tmp_path / "output"

    def fake_run(command, **kwargs):
        output.mkdir(parents=True)
        with (output / "predictions.npz").open("wb") as handle:
            np.savez_compressed(
                handle,
                predictions=np.ones((5, 1, 10, 6), dtype=np.float32),
                symbols=np.asarray(["A"]),
            )
        (output / "runtime_result.json").write_text(
            json.dumps(
                {
                    "prediction_content_sha256": "wrong",
                    "predictions_npz_sha256": sha256_file(output / "predictions.npz"),
                    "path_count": 5,
                    "symbol_count": 1,
                }
            )
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    with pytest.raises(SignalSubprocessError, match="content hash"):
        run_signal_subprocess(
            repo_root=tmp_path,
            input_dir=tmp_path / "input",
            output_dir=output,
            run=fake_run,
        )


def test_runtime_publishes_predictions_atomically_with_auditable_hashes(tmp_path):
    values = np.arange(5 * 2 * 10 * 6, dtype=np.float32).reshape(5, 2, 10, 6)
    result = publish_prediction_artifacts(
        output_dir=tmp_path,
        predictions=values,
        symbols=np.asarray(["A", "B"]),
        seeds=[101, 211, 307, 401, 503],
        batch_sizes=[2, 2, 2, 2, 2],
        runtime_seconds=1.25,
        input_content_sha256="input-sha",
    )
    assert result["path_count"] == 5
    assert result["symbol_count"] == 2
    assert result["input_content_sha256"] == "input-sha"
    assert not list(tmp_path.glob(".*.tmp"))
    saved = np.load(tmp_path / "predictions.npz", allow_pickle=False)
    assert np.array_equal(saved["predictions"], values)
    assert json.loads((tmp_path / "runtime_result.json").read_text()) == result
