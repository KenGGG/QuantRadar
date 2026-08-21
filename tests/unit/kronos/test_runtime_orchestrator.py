from __future__ import annotations

import datetime as dt
import hashlib
import json

from quantradar.kronos.runtime.contracts import (
    KRONOS_MODEL_ID,
    KRONOS_MODEL_REVISION,
    KRONOS_SOURCE_COMMIT,
    KRONOS_TOKENIZER_ID,
    KRONOS_TOKENIZER_REVISION,
    REQUIRED_STAGES,
)
from quantradar.kronos.runtime.orchestrator import run_gpu_smoke
from quantradar.kronos.runtime.report import publish_runtime_reports
from quantradar.kronos.runtime.subprocess_runner import RuntimeSubprocessError


def _passing_runtime_result(eligible: int = 240) -> dict:
    stages = []
    for spec in REQUIRED_STAGES:
        count = spec.symbol_count or eligible
        stages.append(
            {
                "name": spec.name,
                "status": "PASS",
                "requested_symbols": count,
                "completed_symbols": count,
                "path_count": spec.path_count,
                "runtime_seconds": 1.0,
                "peak_vram_mb": 1000.0,
                "batch_size": 25,
                "symbols_per_second": float(count),
                "estimated_full_backfill_hours": None,
                "output_hashes": [f"hash-{index}" for index in range(spec.path_count)],
            }
        )
    return {
        "device": "cuda:0",
        "fallback_used": False,
        "model_id": KRONOS_MODEL_ID,
        "model_revision": KRONOS_MODEL_REVISION,
        "tokenizer_id": KRONOS_TOKENIZER_ID,
        "tokenizer_revision": KRONOS_TOKENIZER_REVISION,
        "source_commit": KRONOS_SOURCE_COMMIT,
        "model_lock_verified": True,
        "source_lock_verified": True,
        "eligible_symbol_count": eligible,
        "input_content_sha256": "input-hash",
        "environment": {"gpu": "RTX 4070 SUPER"},
        "stages": stages,
        "determinism": {
            "passed": True,
            "first_hash": "same",
            "repeat_hash": "same",
        },
        "batch_consistency": {"passed": True, "max_abs_diff": 0.0},
    }


def test_publish_runtime_reports_is_atomic_and_hashes_every_evidence_file(tmp_path) -> None:
    output = tmp_path / "runtime_smoke"
    result = _passing_runtime_result()
    gate = {
        "runtime_ready": True,
        "status": "PASS",
        "reasons": [],
        "completion_marker": "KRONOS_BASE_GPU_RUNTIME_PASS",
    }
    input_manifest = {"eligible_symbol_count": 240, "data_commit": "abc"}

    manifest = publish_runtime_reports(
        output_dir=output,
        runtime_result=result,
        runtime_gate=gate,
        input_manifest=input_manifest,
        generated_at=dt.datetime(2026, 8, 21, tzinfo=dt.timezone.utc),
    )

    assert manifest["completion_marker"] == "KRONOS_BASE_GPU_RUNTIME_PASS"
    assert sorted(manifest["content_hashes"]) == [
        "batch_consistency.json",
        "benchmark.json",
        "determinism.json",
        "environment.json",
        "input_manifest.json",
        "runtime_gate.json",
    ]
    for name, expected in manifest["content_hashes"].items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == expected


def test_orchestrator_builds_inputs_runs_subprocess_and_publishes_pass(tmp_path) -> None:
    calls: list[str] = []

    def input_builder(provider, *, output_dir, data_contract_path):
        calls.append("input")
        return {"eligible_symbol_count": 240, "data_commit": "abc"}

    def runtime_runner(**kwargs):
        calls.append("runtime")
        return _passing_runtime_result()

    outcome = run_gpu_smoke(
        object(),
        repo_root=tmp_path,
        output_dir=tmp_path / "reports",
        input_builder=input_builder,
        runtime_runner=runtime_runner,
        generated_at=dt.datetime(2026, 8, 21, tzinfo=dt.timezone.utc),
    )

    assert calls == ["input", "runtime"]
    assert outcome["gate"]["runtime_ready"] is True
    assert json.loads((tmp_path / "reports/runtime_gate.json").read_text())[
        "completion_marker"
    ] == "KRONOS_BASE_GPU_RUNTIME_PASS"


def test_orchestrator_publishes_blocked_report_when_runtime_fails(tmp_path) -> None:
    def input_builder(provider, *, output_dir, data_contract_path):
        return {"eligible_symbol_count": 240, "data_commit": "abc"}

    def runtime_runner(**kwargs):
        raise RuntimeSubprocessError("CUDA unavailable")

    outcome = run_gpu_smoke(
        object(),
        repo_root=tmp_path,
        output_dir=tmp_path / "reports",
        input_builder=input_builder,
        runtime_runner=runtime_runner,
        generated_at=dt.datetime(2026, 8, 21, tzinfo=dt.timezone.utc),
    )

    assert outcome["gate"]["runtime_ready"] is False
    assert outcome["runtime_result"]["error"] == "CUDA unavailable"
    assert (tmp_path / "reports/runtime_manifest.json").is_file()
