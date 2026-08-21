from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable

import numpy as np

REPO_IMPORT_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_IMPORT_ROOT))

from kronos_runtime.model_lock import (  # noqa: E402
    KRONOS_MODEL_ID,
    KRONOS_MODEL_REVISION,
    KRONOS_SOURCE_COMMIT,
    KRONOS_TOKENIZER_ID,
    KRONOS_TOKENIZER_REVISION,
    collect_environment,
    validate_lock,
)
from kronos_runtime.runner import (  # noqa: E402
    FIXED_PATH_SEEDS,
    _array_content_hash,
    _load_inputs,
    _predict_path,
    _sha256_file,
    require_cuda,
)


def publish_prediction_artifacts(
    *,
    output_dir: str | Path,
    predictions: np.ndarray,
    symbols: np.ndarray,
    seeds: Iterable[int],
    batch_sizes: Iterable[int],
    runtime_seconds: float,
    input_content_sha256: str,
    environment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    prediction_values = np.asarray(predictions, dtype=np.float32)
    symbol_values = np.asarray(symbols)
    npz_path = output / "predictions.npz"
    npz_temp = output / ".predictions.npz.tmp"
    with npz_temp.open("wb") as handle:
        np.savez_compressed(
            handle, predictions=prediction_values, symbols=symbol_values
        )
    os.replace(npz_temp, npz_path)
    seed_values = [int(seed) for seed in seeds]
    batch_values = [int(size) for size in batch_sizes]
    result = {
        "device": "cuda:0",
        "model_id": KRONOS_MODEL_ID,
        "model_revision": KRONOS_MODEL_REVISION,
        "tokenizer_id": KRONOS_TOKENIZER_ID,
        "tokenizer_revision": KRONOS_TOKENIZER_REVISION,
        "source_commit": KRONOS_SOURCE_COMMIT,
        "path_count": int(prediction_values.shape[0]),
        "symbol_count": int(prediction_values.shape[1]),
        "seeds": seed_values,
        "batch_sizes": batch_values,
        "runtime_seconds": float(runtime_seconds),
        "input_content_sha256": input_content_sha256,
        "prediction_content_sha256": _array_content_hash(
            {"predictions": prediction_values, "symbols": symbol_values}
        ),
        "predictions_npz_sha256": _sha256_file(npz_path),
        "environment": environment or {},
    }
    result_path = output / "runtime_result.json"
    result_temp = output / ".runtime_result.json.tmp"
    result_temp.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(result_temp, result_path)
    return result


def _source_commit(source_root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def execute_signal_runtime(
    *, repo_root: Path, input_dir: Path, output_dir: Path, initial_batch_size: int
) -> dict[str, Any]:
    os.environ.update(
        {
            "HF_HUB_OFFLINE": "1",
            "HF_DATASETS_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "CUBLAS_WORKSPACE_CONFIG": ":4096:8",
        }
    )
    import pandas as pd
    import torch

    require_cuda(torch)
    lock = json.loads(
        (repo_root / "models/kronos/kronos_model_lock.json").read_text(
            encoding="utf-8"
        )
    )
    environment = collect_environment()
    errors = validate_lock(lock, repo_root=repo_root, current_environment=environment)
    if errors:
        raise RuntimeError("Model lock verification failed: " + "; ".join(errors))
    source_root = repo_root / lock["source"]["path"]
    if _source_commit(source_root) != KRONOS_SOURCE_COMMIT:
        raise RuntimeError("Kronos source checkout commit changed")
    arrays, input_manifest = _load_inputs(input_dir)
    sys.path.insert(0, str(source_root))
    from model import Kronos, KronosPredictor, KronosTokenizer

    tokenizer = KronosTokenizer.from_pretrained(
        str(repo_root / lock["tokenizer"]["path"])
    ).eval()
    model = Kronos.from_pretrained(str(repo_root / lock["model"]["path"])).eval()
    predictor = KronosPredictor(
        model=model, tokenizer=tokenizer, device="cuda:0", max_context=512
    )
    if predictor.device != "cuda:0":
        raise RuntimeError("Kronos predictor changed device; fallback is forbidden")
    started = time.perf_counter()
    paths = []
    batches = []
    for seed in FIXED_PATH_SEEDS:
        values, batch_size = _predict_path(
            predictor=predictor,
            torch_module=torch,
            pandas_module=pd,
            arrays=arrays,
            symbol_count=len(arrays["symbols"]),
            seed=seed,
            initial_batch_size=initial_batch_size,
        )
        paths.append(values)
        batches.append(batch_size)
    torch.cuda.synchronize()
    return publish_prediction_artifacts(
        output_dir=output_dir,
        predictions=np.stack(paths),
        symbols=arrays["symbols"],
        seeds=FIXED_PATH_SEEDS,
        batch_sizes=batches,
        runtime_seconds=time.perf_counter() - started,
        input_content_sha256=input_manifest["input_content_sha256"],
        environment=environment,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate locked Kronos signal paths")
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--initial-batch-size", type=int, default=50)
    args = parser.parse_args(argv)
    result = execute_signal_runtime(
        repo_root=args.repo_root.resolve(),
        input_dir=args.input_dir.resolve(),
        output_dir=args.output_dir.resolve(),
        initial_batch_size=args.initial_batch_size,
    )
    print(json.dumps({"symbols": result["symbol_count"], "paths": result["path_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
