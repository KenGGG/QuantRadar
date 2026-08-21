from __future__ import annotations

from copy import deepcopy

from quantradar.kronos.runtime.contracts import (
    FIXED_PATH_SEEDS,
    KRONOS_MODEL_ID,
    KRONOS_MODEL_REVISION,
    KRONOS_SOURCE_COMMIT,
    KRONOS_TOKENIZER_ID,
    KRONOS_TOKENIZER_REVISION,
    REQUIRED_STAGES,
)
from quantradar.kronos.runtime.gates import evaluate_runtime_gate


def _passing_result() -> dict:
    eligible = 287
    stages = []
    for spec in REQUIRED_STAGES:
        symbol_count = spec.symbol_count or eligible
        stages.append(
            {
                "name": spec.name,
                "status": "PASS",
                "requested_symbols": symbol_count,
                "completed_symbols": symbol_count,
                "path_count": spec.path_count,
                "output_hashes": [f"hash-{index}" for index in range(spec.path_count)],
                "runtime_seconds": 1.0,
                "peak_vram_mb": 1024.0,
                "batch_size": 50,
                "symbols_per_second": float(symbol_count),
                "estimated_full_backfill_hours": None,
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
        "stages": stages,
        "determinism": {
            "passed": True,
            "first_hash": "same",
            "repeat_hash": "same",
        },
    }


def test_goal1_identifiers_and_stage_order_are_immutable() -> None:
    assert KRONOS_SOURCE_COMMIT == "67b630e67f6a18c9e9be918d9b4337c960db1e9a"
    assert KRONOS_MODEL_REVISION == "2b554741eca47781b64468546e77fef3e85130e6"
    assert KRONOS_TOKENIZER_REVISION == "0e0117387f39004a9016484a186a908917e22426"
    assert FIXED_PATH_SEEDS == (101, 211, 307, 401, 503)
    assert [stage.name for stage in REQUIRED_STAGES] == [
        "one_symbol_one_path",
        "fifty_symbols_one_path",
        "full_pit_one_path",
        "full_pit_five_paths",
    ]


def test_runtime_gate_passes_only_complete_cuda_base_result() -> None:
    gate = evaluate_runtime_gate(_passing_result())

    assert gate["runtime_ready"] is True
    assert gate["status"] == "PASS"
    assert gate["completion_marker"] == "KRONOS_BASE_GPU_RUNTIME_PASS"
    assert gate["reasons"] == []


def test_runtime_gate_rejects_cpu_or_fallback() -> None:
    result = _passing_result()
    result["device"] = "cpu"
    result["fallback_used"] = True

    gate = evaluate_runtime_gate(result)

    assert gate["runtime_ready"] is False
    assert gate["completion_marker"] is None
    assert any("CUDA" in reason for reason in gate["reasons"])
    assert any("fallback" in reason for reason in gate["reasons"])


def test_runtime_gate_rejects_wrong_model_and_incomplete_stage() -> None:
    result = _passing_result()
    result["model_id"] = "NeoQuasar/Kronos-small"
    result["stages"][2]["completed_symbols"] -= 1

    gate = evaluate_runtime_gate(result)

    assert gate["runtime_ready"] is False
    assert any("Kronos-base" in reason for reason in gate["reasons"])
    assert any("full_pit_one_path" in reason for reason in gate["reasons"])


def test_runtime_gate_rejects_changed_hashes_or_nondeterminism() -> None:
    result = deepcopy(_passing_result())
    result["model_lock_verified"] = False
    result["determinism"]["repeat_hash"] = "different"

    gate = evaluate_runtime_gate(result)

    assert gate["runtime_ready"] is False
    assert any("model lock" in reason for reason in gate["reasons"])
    assert any("determin" in reason.lower() for reason in gate["reasons"])
