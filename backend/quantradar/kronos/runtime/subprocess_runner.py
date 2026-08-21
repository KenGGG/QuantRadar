from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping


class RuntimeSubprocessError(RuntimeError):
    pass


def build_runtime_command(
    *,
    repo_root: str | Path,
    input_dir: str | Path,
    output_path: str | Path,
    initial_batch_size: int = 50,
) -> list[str]:
    root = Path(repo_root).resolve()
    return [
        str(root / ".venv-kronos/bin/python"),
        str(root / "kronos_runtime/runner.py"),
        "--repo-root",
        str(root),
        "--input-dir",
        str(Path(input_dir).resolve()),
        "--output",
        str(Path(output_path).resolve()),
        "--initial-batch-size",
        str(initial_batch_size),
    ]


def offline_runtime_environment(
    base: Mapping[str, str] | None = None,
) -> dict[str, str]:
    environment = dict(os.environ if base is None else base)
    environment.update(
        {
            "HF_HUB_OFFLINE": "1",
            "HF_DATASETS_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "CUDA_VISIBLE_DEVICES": "0",
            "CUBLAS_WORKSPACE_CONFIG": ":4096:8",
            "TOKENIZERS_PARALLELISM": "false",
        }
    )
    return environment


def run_runtime_subprocess(
    *,
    repo_root: str | Path,
    input_dir: str | Path,
    output_path: str | Path,
    initial_batch_size: int = 50,
    run: Callable = subprocess.run,
) -> dict[str, Any]:
    command = build_runtime_command(
        repo_root=repo_root,
        input_dir=input_dir,
        output_path=output_path,
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
        detail = (completed.stderr or completed.stdout or "unknown runtime failure").strip()
        raise RuntimeSubprocessError(detail)
    target = Path(output_path)
    if not target.is_file():
        raise RuntimeSubprocessError("Kronos runtime did not produce its JSON result")
    try:
        result = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeSubprocessError(f"Invalid Kronos runtime JSON: {exc}") from exc
    if not isinstance(result, dict):
        raise RuntimeSubprocessError("Kronos runtime result must be a JSON object")
    return result
