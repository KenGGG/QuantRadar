from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


def _json_safe(value: Any) -> Any:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(_json_safe(value), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def publish_runtime_reports(
    *,
    output_dir: str | Path,
    runtime_result: dict[str, Any],
    runtime_gate: dict[str, Any],
    input_manifest: dict[str, Any],
    generated_at: dt.datetime,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    backup = output.with_name(f".{output.name}.previous")
    try:
        _write_json(
            stage / "benchmark.json",
            {
                "eligible_symbol_count": runtime_result.get("eligible_symbol_count"),
                "stages": runtime_result.get("stages", []),
                "error": runtime_result.get("error"),
            },
        )
        _write_json(stage / "determinism.json", runtime_result.get("determinism", {}))
        _write_json(
            stage / "batch_consistency.json",
            runtime_result.get("batch_consistency", {}),
        )
        _write_json(stage / "environment.json", runtime_result.get("environment", {}))
        _write_json(stage / "input_manifest.json", input_manifest)
        _write_json(stage / "runtime_gate.json", runtime_gate)
        evidence_names = sorted(path.name for path in stage.iterdir())
        manifest = {
            "goal": "Goal 1 - Kronos-base runtime and real GPU smoke",
            "generated_at": generated_at,
            "completion_marker": runtime_gate.get("completion_marker"),
            "runtime_ready": runtime_gate.get("runtime_ready", False),
            "model_id": runtime_result.get("model_id"),
            "model_revision": runtime_result.get("model_revision"),
            "tokenizer_revision": runtime_result.get("tokenizer_revision"),
            "source_commit": runtime_result.get("source_commit"),
            "input_content_sha256": runtime_result.get("input_content_sha256"),
            "content_hashes": {
                name: _sha256(stage / name) for name in evidence_names
            },
        }
        _write_json(stage / "runtime_manifest.json", manifest)
        if backup.exists():
            shutil.rmtree(backup)
        if output.exists():
            os.replace(output, backup)
        os.replace(stage, output)
        if backup.exists():
            shutil.rmtree(backup)
        return manifest
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        if backup.exists() and not output.exists():
            os.replace(backup, output)
        raise
