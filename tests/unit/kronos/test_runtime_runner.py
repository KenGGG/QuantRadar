from __future__ import annotations

import json
import subprocess

import numpy as np
import pytest

from kronos_runtime.runner import (
    compare_batch_predictions,
    next_batch_size_after_oom,
    require_cuda,
    stage_plan,
)
from quantradar.kronos.runtime.subprocess_runner import (
    RuntimeSubprocessError,
    build_runtime_command,
    offline_runtime_environment,
    run_runtime_subprocess,
)


class _UnavailableCuda:
    @staticmethod
    def is_available() -> bool:
        return False


class _CpuOnlyTorch:
    cuda = _UnavailableCuda()


def test_stage_plan_is_ordered_and_requires_fifty_symbols() -> None:
    with pytest.raises(ValueError, match="at least 50"):
        stage_plan(49)

    assert stage_plan(287) == [
        ("one_symbol_one_path", 1, (101,)),
        ("fifty_symbols_one_path", 50, (101,)),
        ("full_pit_one_path", 287, (101,)),
        ("full_pit_five_paths", 287, (101, 211, 307, 401, 503)),
    ]


def test_cuda_requirement_never_falls_back_to_cpu() -> None:
    with pytest.raises(RuntimeError, match="CPU fallback is forbidden"):
        require_cuda(_CpuOnlyTorch())


def test_oom_reduction_halves_batch_and_stops_at_one() -> None:
    assert next_batch_size_after_oom(50) == 25
    assert next_batch_size_after_oom(3) == 1
    with pytest.raises(RuntimeError, match="batch size 1"):
        next_batch_size_after_oom(1)


def test_batch_serial_comparison_uses_explicit_numeric_tolerance() -> None:
    batch = np.ones((5, 10, 6), dtype=np.float32)
    serial = batch.copy()
    serial[0, 0, 0] += 1e-6

    comparison = compare_batch_predictions(batch, serial)

    assert comparison["passed"] is True
    serial[0, 0, 0] += 1e-2
    assert compare_batch_predictions(batch, serial)["passed"] is False


def test_parent_command_uses_only_isolated_python_and_offline_flags(tmp_path) -> None:
    command = build_runtime_command(
        repo_root=tmp_path,
        input_dir=tmp_path / "inputs",
        output_path=tmp_path / "result.json",
        initial_batch_size=25,
    )
    environment = offline_runtime_environment({"PATH": "/usr/bin"})

    assert command[0] == str(tmp_path / ".venv-kronos/bin/python")
    assert command[1] == str(tmp_path / "kronos_runtime/runner.py")
    assert command[-2:] == ["--initial-batch-size", "25"]
    assert environment["HF_HUB_OFFLINE"] == "1"
    assert environment["TRANSFORMERS_OFFLINE"] == "1"
    assert environment["CUDA_VISIBLE_DEVICES"] == "0"
    assert environment["CUBLAS_WORKSPACE_CONFIG"] == ":4096:8"


def test_parent_reads_valid_json_result_without_importing_torch(tmp_path) -> None:
    output = tmp_path / "result.json"

    def fake_run(command, **kwargs):
        output.write_text(json.dumps({"device": "cuda:0", "stages": []}))
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    result = run_runtime_subprocess(
        repo_root=tmp_path,
        input_dir=tmp_path / "inputs",
        output_path=output,
        run=fake_run,
    )

    assert result["device"] == "cuda:0"


def test_parent_exposes_runtime_failure_instead_of_fallback(tmp_path) -> None:
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 2, stdout="", stderr="CUDA OOM")

    with pytest.raises(RuntimeSubprocessError, match="CUDA OOM"):
        run_runtime_subprocess(
            repo_root=tmp_path,
            input_dir=tmp_path / "inputs",
            output_path=tmp_path / "result.json",
            run=fake_run,
        )
