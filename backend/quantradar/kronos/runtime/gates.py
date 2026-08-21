from __future__ import annotations

from typing import Any

from .contracts import (
    KRONOS_MODEL_ID,
    KRONOS_MODEL_REVISION,
    KRONOS_SOURCE_COMMIT,
    KRONOS_TOKENIZER_ID,
    KRONOS_TOKENIZER_REVISION,
    REQUIRED_STAGES,
)


def evaluate_runtime_gate(result: dict[str, Any]) -> dict[str, Any]:
    """Evaluate only real, immutable, CUDA-only Goal 1 evidence."""
    reasons: list[str] = []
    if not str(result.get("device", "")).startswith("cuda"):
        reasons.append("CUDA device was not used")
    if result.get("fallback_used") is not False:
        reasons.append("A device or model fallback was used")
    if result.get("model_id") != KRONOS_MODEL_ID:
        reasons.append("The loaded model is not the locked Kronos-base model")
    if result.get("model_revision") != KRONOS_MODEL_REVISION:
        reasons.append("Kronos-base revision does not match the immutable lock")
    if result.get("tokenizer_id") != KRONOS_TOKENIZER_ID:
        reasons.append("Tokenizer identity does not match the immutable lock")
    if result.get("tokenizer_revision") != KRONOS_TOKENIZER_REVISION:
        reasons.append("Tokenizer revision does not match the immutable lock")
    if result.get("source_commit") != KRONOS_SOURCE_COMMIT:
        reasons.append("Kronos source commit does not match the immutable lock")
    if result.get("model_lock_verified") is not True:
        reasons.append("The model lock was not verified")
    if result.get("source_lock_verified") is not True:
        reasons.append("The source lock was not verified")

    eligible = result.get("eligible_symbol_count")
    if not isinstance(eligible, int) or eligible < 50:
        reasons.append("Fewer than 50 eligible PIT symbols were available")
        eligible = 0

    stages = result.get("stages")
    if not isinstance(stages, list):
        stages = []
        reasons.append("Benchmark stages are missing")
    if [stage.get("name") for stage in stages] != [spec.name for spec in REQUIRED_STAGES]:
        reasons.append("Benchmark stages are missing or out of order")

    for spec, stage in zip(REQUIRED_STAGES, stages):
        expected_symbols = spec.symbol_count or eligible
        if stage.get("status") != "PASS":
            reasons.append(f"{spec.name} did not pass")
        if stage.get("requested_symbols") != expected_symbols:
            reasons.append(f"{spec.name} requested the wrong symbol count")
        if stage.get("completed_symbols") != expected_symbols:
            reasons.append(f"{spec.name} did not complete every symbol")
        if stage.get("path_count") != spec.path_count:
            reasons.append(f"{spec.name} used the wrong path count")
        hashes = stage.get("output_hashes")
        if not isinstance(hashes, list) or len(hashes) != spec.path_count:
            reasons.append(f"{spec.name} did not preserve every path hash")
        for metric in ("runtime_seconds", "peak_vram_mb", "batch_size", "symbols_per_second"):
            value = stage.get(metric)
            if not isinstance(value, (int, float)) or value <= 0:
                reasons.append(f"{spec.name} has invalid {metric}")

    determinism = result.get("determinism") or {}
    if (
        determinism.get("passed") is not True
        or not determinism.get("first_hash")
        or determinism.get("first_hash") != determinism.get("repeat_hash")
    ):
        reasons.append("Fixed-seed output is not deterministic")
    batch_consistency = result.get("batch_consistency") or {}
    if batch_consistency.get("passed") is not True:
        reasons.append("Batch and per-symbol predictions differ beyond tolerance")

    ready = not reasons
    return {
        "runtime_ready": ready,
        "status": "PASS" if ready else "BLOCKED",
        "reasons": reasons,
        "completion_marker": "KRONOS_BASE_GPU_RUNTIME_PASS" if ready else None,
    }
