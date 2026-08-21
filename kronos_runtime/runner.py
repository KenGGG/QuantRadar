from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

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

FEATURE_NAMES = ("open", "high", "low", "close", "volume", "amount")
FIXED_PATH_SEEDS = (101, 211, 307, 401, 503)


def stage_plan(eligible_symbol_count: int) -> list[tuple[str, int, tuple[int, ...]]]:
    if eligible_symbol_count < 50:
        raise ValueError("Goal 1 requires at least 50 eligible PIT symbols")
    return [
        ("one_symbol_one_path", 1, (FIXED_PATH_SEEDS[0],)),
        ("fifty_symbols_one_path", 50, (FIXED_PATH_SEEDS[0],)),
        ("full_pit_one_path", eligible_symbol_count, (FIXED_PATH_SEEDS[0],)),
        ("full_pit_five_paths", eligible_symbol_count, FIXED_PATH_SEEDS),
    ]


def require_cuda(torch_module: Any) -> None:
    if not torch_module.cuda.is_available():
        raise RuntimeError("CUDA is unavailable; CPU fallback is forbidden")


def next_batch_size_after_oom(current: int) -> int:
    if current <= 1:
        raise RuntimeError("Kronos-base exhausted GPU memory at batch size 1")
    return max(1, current // 2)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_bytes(digest: Any, value: bytes) -> None:
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def _array_content_hash(arrays: dict[str, np.ndarray]) -> str:
    digest = hashlib.sha256()
    for name in sorted(arrays):
        value = np.ascontiguousarray(arrays[name])
        _hash_bytes(digest, name.encode("utf-8"))
        _hash_bytes(digest, value.dtype.str.encode("ascii"))
        _hash_bytes(digest, json.dumps(value.shape).encode("ascii"))
        _hash_bytes(digest, value.tobytes())
    return digest.hexdigest()


def _load_inputs(input_dir: Path) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    npz_path = input_dir / "runtime_inputs.npz"
    manifest_path = input_dir / "input_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if _sha256_file(npz_path) != manifest.get("npz_sha256"):
        raise RuntimeError("Runtime input NPZ SHA256 mismatch")
    with np.load(npz_path, allow_pickle=False) as loaded:
        arrays = {name: loaded[name] for name in loaded.files}
    if _array_content_hash(arrays) != manifest.get("input_content_sha256"):
        raise RuntimeError("Runtime input content SHA256 mismatch")
    expected = (manifest.get("eligible_symbol_count"), 90, len(FEATURE_NAMES))
    if arrays.get("values") is None or arrays["values"].shape != expected:
        raise RuntimeError(f"Runtime input shape does not match {expected}")
    if arrays.get("y_dates") is None or arrays["y_dates"].shape != (10,):
        raise RuntimeError("Runtime input must contain 10 future trading dates")
    return arrays, manifest


def _set_seed(torch_module: Any, seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch_module.manual_seed(seed)
    torch_module.cuda.manual_seed_all(seed)
    torch_module.backends.cudnn.deterministic = True
    torch_module.backends.cudnn.benchmark = False
    torch_module.use_deterministic_algorithms(True)


def _prediction_hash(symbols: np.ndarray, values: np.ndarray) -> str:
    return _array_content_hash(
        {
            "symbols": np.asarray(symbols),
            "predictions": np.asarray(values, dtype=np.float32),
        }
    )


def _is_cuda_oom(exc: BaseException, torch_module: Any) -> bool:
    oom_type = getattr(torch_module.cuda, "OutOfMemoryError", ())
    return (isinstance(oom_type, type) and isinstance(exc, oom_type)) or (
        "out of memory" in str(exc).lower()
    )


def _predict_path(
    *,
    predictor: Any,
    torch_module: Any,
    pandas_module: Any,
    arrays: dict[str, np.ndarray],
    symbol_count: int,
    seed: int,
    initial_batch_size: int,
) -> tuple[np.ndarray, int]:
    batch_size = min(initial_batch_size, symbol_count)
    while True:
        _set_seed(torch_module, seed)
        predictions: list[np.ndarray] = []
        try:
            with torch_module.inference_mode():
                for start in range(0, symbol_count, batch_size):
                    end = min(start + batch_size, symbol_count)
                    frames = [
                        pandas_module.DataFrame(
                            arrays["values"][index], columns=FEATURE_NAMES
                        )
                        for index in range(start, end)
                    ]
                    x_timestamps = [
                        pandas_module.Series(
                            pandas_module.to_datetime(arrays["x_dates"][index])
                        )
                        for index in range(start, end)
                    ]
                    y_timestamps = [
                        pandas_module.Series(
                            pandas_module.to_datetime(arrays["y_dates"])
                        )
                        for _ in range(start, end)
                    ]
                    outputs = predictor.predict_batch(
                        frames,
                        x_timestamps,
                        y_timestamps,
                        pred_len=10,
                        T=0.6,
                        top_k=0,
                        top_p=0.9,
                        sample_count=1,
                        verbose=False,
                    )
                    predictions.extend(
                        frame.loc[:, list(FEATURE_NAMES)].to_numpy(dtype=np.float32)
                        for frame in outputs
                    )
            return np.stack(predictions), batch_size
        except BaseException as exc:
            if not _is_cuda_oom(exc, torch_module):
                raise
            batch_size = next_batch_size_after_oom(batch_size)
            predictions.clear()
            torch_module.cuda.empty_cache()


def _benchmark_stage(
    *,
    name: str,
    symbol_count: int,
    seeds: tuple[int, ...],
    predictor: Any,
    torch_module: Any,
    pandas_module: Any,
    arrays: dict[str, np.ndarray],
    initial_batch_size: int,
    available_pit_signal_weeks: int | None,
) -> tuple[dict[str, Any], dict[int, np.ndarray]]:
    torch_module.cuda.empty_cache()
    torch_module.cuda.reset_peak_memory_stats()
    torch_module.cuda.synchronize()
    started = time.perf_counter()
    path_hashes: list[str] = []
    path_values: dict[int, np.ndarray] = {}
    actual_batches: list[int] = []
    for seed in seeds:
        values, actual_batch = _predict_path(
            predictor=predictor,
            torch_module=torch_module,
            pandas_module=pandas_module,
            arrays=arrays,
            symbol_count=symbol_count,
            seed=seed,
            initial_batch_size=initial_batch_size,
        )
        path_values[seed] = values
        path_hashes.append(_prediction_hash(arrays["symbols"][:symbol_count], values))
        actual_batches.append(actual_batch)
    torch_module.cuda.synchronize()
    runtime = time.perf_counter() - started
    backfill = None
    if name == "full_pit_five_paths" and available_pit_signal_weeks:
        backfill = runtime * int(available_pit_signal_weeks) / 3600.0
    return (
        {
            "name": name,
            "status": "PASS",
            "requested_symbols": symbol_count,
            "completed_symbols": symbol_count,
            "path_count": len(seeds),
            "seeds": list(seeds),
            "runtime_seconds": runtime,
            "peak_vram_mb": torch_module.cuda.max_memory_allocated() / (1024 * 1024),
            "batch_size": min(actual_batches),
            "symbols_per_second": symbol_count * len(seeds) / runtime,
            "estimated_full_backfill_hours": backfill,
            "output_hashes": path_hashes,
        },
        path_values,
    )


def _source_commit(source_root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def execute_runtime(
    *, repo_root: Path, input_dir: Path, initial_batch_size: int
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
    lock_path = repo_root / "models/kronos/kronos_model_lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    environment = collect_environment()
    lock_errors = validate_lock(
        lock, repo_root=repo_root, current_environment=environment
    )
    if lock_errors:
        raise RuntimeError("Model lock verification failed: " + "; ".join(lock_errors))
    source_root = repo_root / lock["source"]["path"]
    if _source_commit(source_root) != KRONOS_SOURCE_COMMIT:
        raise RuntimeError("Kronos source checkout commit changed")
    arrays, input_manifest = _load_inputs(input_dir)

    sys.path.insert(0, str(source_root))
    from model import Kronos, KronosPredictor, KronosTokenizer

    tokenizer_path = repo_root / lock["tokenizer"]["path"]
    model_path = repo_root / lock["model"]["path"]
    tokenizer = KronosTokenizer.from_pretrained(str(tokenizer_path)).eval()
    model = Kronos.from_pretrained(str(model_path)).eval()
    predictor = KronosPredictor(
        model=model, tokenizer=tokenizer, device="cuda:0", max_context=512
    )
    if predictor.device != "cuda:0":
        raise RuntimeError("Kronos predictor changed device; fallback is forbidden")

    stages: list[dict[str, Any]] = []
    first_path_values = None
    available_weeks = input_manifest.get("available_pit_signal_weeks")
    for name, count, seeds in stage_plan(len(arrays["symbols"])):
        stage, path_values = _benchmark_stage(
            name=name,
            symbol_count=count,
            seeds=seeds,
            predictor=predictor,
            torch_module=torch,
            pandas_module=pd,
            arrays=arrays,
            initial_batch_size=initial_batch_size,
            available_pit_signal_weeks=available_weeks,
        )
        stages.append(stage)
        if name == "one_symbol_one_path":
            first_path_values = path_values[FIXED_PATH_SEEDS[0]]

    repeated_values, repeat_batch = _predict_path(
        predictor=predictor,
        torch_module=torch,
        pandas_module=pd,
        arrays=arrays,
        symbol_count=1,
        seed=FIXED_PATH_SEEDS[0],
        initial_batch_size=initial_batch_size,
    )
    first_hash = _prediction_hash(arrays["symbols"][:1], first_path_values)
    repeat_hash = _prediction_hash(arrays["symbols"][:1], repeated_values)
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
        "eligible_symbol_count": len(arrays["symbols"]),
        "input_content_sha256": input_manifest["input_content_sha256"],
        "environment": environment,
        "stages": stages,
        "determinism": {
            "passed": first_hash == repeat_hash,
            "seed": FIXED_PATH_SEEDS[0],
            "batch_size": repeat_batch,
            "first_hash": first_hash,
            "repeat_hash": repeat_hash,
        },
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run locked Kronos-base CUDA smoke")
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--initial-batch-size", type=int, default=50)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = execute_runtime(
        repo_root=args.repo_root.resolve(),
        input_dir=args.input_dir.resolve(),
        initial_batch_size=args.initial_batch_size,
    )
    _write_json(args.output.resolve(), result)
    print(json.dumps({"device": result["device"], "stages": len(result["stages"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
