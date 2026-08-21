from __future__ import annotations

import json
import subprocess

from kronos_runtime.model_lock import (
    build_lock_document,
    hash_files,
    validate_lock,
    write_lock,
)
from quantradar.kronos.runtime.contracts import (
    KRONOS_MODEL_REVISION,
    KRONOS_SOURCE_COMMIT,
    KRONOS_TOKENIZER_REVISION,
)
from scripts.setup_kronos_runtime import setup_runtime


def _environment() -> dict:
    return {
        "python": "3.12.3",
        "torch": "2.8.0+cu128",
        "cuda": "12.8",
        "cudnn": "91002",
        "driver": "595.84",
        "gpu": "NVIDIA GeForce RTX 4070 SUPER",
        "compute_capability": "8.9",
        "pip_freeze": ["torch==2.8.0"],
    }


def test_hash_files_covers_every_runtime_file_and_ignores_cache(tmp_path) -> None:
    (tmp_path / "config.json").write_text("{}")
    (tmp_path / "model.safetensors").write_bytes(b"weights")
    (tmp_path / ".cache").mkdir()
    (tmp_path / ".cache" / "metadata").write_text("mutable")

    hashes = hash_files(tmp_path)

    assert sorted(hashes) == ["config.json", "model.safetensors"]
    assert all(len(value) == 64 for value in hashes.values())


def test_lock_records_immutable_revisions_files_and_cuda_environment(tmp_path) -> None:
    source = tmp_path / "source"
    model = tmp_path / "model"
    tokenizer = tmp_path / "tokenizer"
    for directory in (source, model, tokenizer):
        directory.mkdir()
        (directory / "config.json").write_text(directory.name)
    requirements = tmp_path / "requirements.lock"
    requirements.write_text("torch==2.8.0\n")

    lock = build_lock_document(
        repo_root=tmp_path,
        source_root=source,
        model_root=model,
        tokenizer_root=tokenizer,
        requirements_path=requirements,
        environment=_environment(),
        source_commit=KRONOS_SOURCE_COMMIT,
        model_created_at="2025-09-09T14:08:15+00:00",
        tokenizer_created_at="2025-09-09T14:10:02+00:00",
        created_at="2026-08-21T00:00:00+00:00",
    )

    assert lock["source"]["commit"] == KRONOS_SOURCE_COMMIT
    assert lock["model"]["revision"] == KRONOS_MODEL_REVISION
    assert lock["tokenizer"]["revision"] == KRONOS_TOKENIZER_REVISION
    assert lock["environment"]["gpu"] == "NVIDIA GeForce RTX 4070 SUPER"
    assert lock["model"]["max_context"] == 512
    assert lock["requirements"]["sha256"]


def test_validate_lock_detects_file_mutation_and_environment_mismatch(tmp_path) -> None:
    source = tmp_path / "source"
    model = tmp_path / "model"
    tokenizer = tmp_path / "tokenizer"
    for directory in (source, model, tokenizer):
        directory.mkdir()
        (directory / "config.json").write_text(directory.name)
    requirements = tmp_path / "requirements.lock"
    requirements.write_text("torch==2.8.0\n")
    lock = build_lock_document(
        repo_root=tmp_path,
        source_root=source,
        model_root=model,
        tokenizer_root=tokenizer,
        requirements_path=requirements,
        environment=_environment(),
        source_commit=KRONOS_SOURCE_COMMIT,
        model_created_at="2025-09-09T14:08:15+00:00",
        tokenizer_created_at="2025-09-09T14:10:02+00:00",
        created_at="2026-08-21T00:00:00+00:00",
    )
    (model / "config.json").write_text("changed")
    current = _environment()
    current["gpu"] = "CPU"

    errors = validate_lock(lock, repo_root=tmp_path, current_environment=current)

    assert any("model/config.json" in error for error in errors)
    assert any("environment.gpu" in error for error in errors)


def test_write_lock_round_trips_canonical_json(tmp_path) -> None:
    target = tmp_path / "lock.json"
    write_lock(target, {"z": 1, "a": 2})

    assert json.loads(target.read_text()) == {"a": 2, "z": 1}
    assert target.read_text().endswith("\n")


def test_setup_uses_isolated_venv_exact_source_and_lock_preparation(tmp_path) -> None:
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append([str(value) for value in command])
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    setup_runtime(tmp_path, run=fake_run, bootstrap_python="python3")

    assert calls[0] == ["python3", "-m", "venv", str(tmp_path / ".venv-kronos")]
    assert calls[1] == [
        str(tmp_path / ".venv-kronos/bin/python"),
        "-m",
        "pip",
        "install",
        "--requirement",
        str(tmp_path / "kronos_runtime/requirements.lock"),
    ]
    assert KRONOS_SOURCE_COMMIT in calls[3]
    assert calls[-1][-3:] == ["prepare", "--repo-root", str(tmp_path)]
