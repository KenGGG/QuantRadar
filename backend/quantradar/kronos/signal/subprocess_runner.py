from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Callable

import numpy as np

from quantradar.kronos.runtime.inputs import array_content_hash, sha256_file
from quantradar.kronos.runtime.subprocess_runner import offline_runtime_environment


class SignalSubprocessError(RuntimeError):
    pass


def build_signal_command(
    *,
    repo_root: str | Path,
    input_dir: str | Path,
    output_dir: str | Path,
    initial_batch_size: int = 50,
) -> list[str]:
    root = Path(repo_root).resolve()
    return [
        str(root / ".venv-kronos/bin/python"),
        str(root / "kronos_runtime/signal_runner.py"),
        "--repo-root",
        str(root),
        "--input-dir",
        str(Path(input_dir).resolve()),
        "--output-dir",
        str(Path(output_dir).resolve()),
        "--initial-batch-size",
        str(initial_batch_size),
    ]


def run_signal_subprocess(
    *,
    repo_root: str | Path,
    input_dir: str | Path,
    output_dir: str | Path,
    initial_batch_size: int = 50,
    run: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    command = build_signal_command(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        initial_batch_size=initial_batch_size,
    )
    completed = run(
        command,
        cwd=str(Path(repo_root).resolve()),
        env=offline_runtime_environment(),
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "unknown signal runtime failure").strip()
        raise SignalSubprocessError(detail)
    output = Path(output_dir)
    result_path = output / "runtime_result.json"
    predictions_path = output / "predictions.npz"
    if not result_path.is_file() or not predictions_path.is_file():
        raise SignalSubprocessError("signal runtime did not produce required artifacts")
    try:
        runtime = json.loads(result_path.read_text(encoding="utf-8"))
        with np.load(predictions_path, allow_pickle=False) as loaded:
            predictions = loaded["predictions"]
            symbols = loaded["symbols"]
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        raise SignalSubprocessError(f"invalid signal runtime artifacts: {exc}") from exc
    if sha256_file(predictions_path) != runtime.get("predictions_npz_sha256"):
        raise SignalSubprocessError("predictions NPZ hash mismatch")
    actual_hash = array_content_hash(
        {"predictions": predictions, "symbols": symbols}
    )
    if actual_hash != runtime.get("prediction_content_sha256"):
        raise SignalSubprocessError("prediction content hash mismatch")
    expected_shape = (
        runtime.get("path_count"),
        runtime.get("symbol_count"),
        10,
        6,
    )
    if predictions.shape != expected_shape or symbols.shape != (expected_shape[1],):
        raise SignalSubprocessError("prediction output shape mismatch")
    return {"runtime": runtime, "predictions": predictions, "symbols": symbols}
