from __future__ import annotations

import datetime as dt
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable

from .contracts import (
    KRONOS_MODEL_ID,
    KRONOS_MODEL_REVISION,
    KRONOS_SOURCE_COMMIT,
    KRONOS_TOKENIZER_ID,
    KRONOS_TOKENIZER_REVISION,
)
from .gates import evaluate_runtime_gate
from .inputs import collect_real_input_package
from .report import publish_runtime_reports
from .subprocess_runner import RuntimeSubprocessError, run_runtime_subprocess


def _blocked_result(input_manifest: dict[str, Any], error: Exception) -> dict[str, Any]:
    return {
        "device": None,
        "fallback_used": False,
        "model_id": KRONOS_MODEL_ID,
        "model_revision": KRONOS_MODEL_REVISION,
        "tokenizer_id": KRONOS_TOKENIZER_ID,
        "tokenizer_revision": KRONOS_TOKENIZER_REVISION,
        "source_commit": KRONOS_SOURCE_COMMIT,
        "model_lock_verified": False,
        "source_lock_verified": False,
        "eligible_symbol_count": input_manifest.get("eligible_symbol_count", 0),
        "input_content_sha256": input_manifest.get("input_content_sha256"),
        "environment": {},
        "stages": [],
        "determinism": {"passed": False},
        "error": str(error),
    }


def run_gpu_smoke(
    provider,
    *,
    repo_root: str | Path,
    output_dir: str | Path,
    input_builder: Callable = collect_real_input_package,
    runtime_runner: Callable = run_runtime_subprocess,
    generated_at: dt.datetime | None = None,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    output = Path(output_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".runtime-smoke-work-", dir=output.parent))
    input_dir = work / "input"
    runtime_output = work / "runtime_result.json"
    try:
        input_manifest = input_builder(
            provider,
            output_dir=input_dir,
            data_contract_path=root / "reports/kronos/data_audit/data_contract.json",
        )
        try:
            runtime_result = runtime_runner(
                repo_root=root,
                input_dir=input_dir,
                output_path=runtime_output,
            )
        except RuntimeSubprocessError as exc:
            runtime_result = _blocked_result(input_manifest, exc)
        gate = evaluate_runtime_gate(runtime_result)
        manifest = publish_runtime_reports(
            output_dir=output,
            runtime_result=runtime_result,
            runtime_gate=gate,
            input_manifest=input_manifest,
            generated_at=generated_at or dt.datetime.now(dt.timezone.utc),
        )
        return {
            "output_dir": str(output),
            "runtime_result": runtime_result,
            "gate": gate,
            "manifest": manifest,
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)
