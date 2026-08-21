from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

KRONOS_SOURCE_COMMIT = "67b630e67f6a18c9e9be918d9b4337c960db1e9a"
KRONOS_MODEL_ID = "NeoQuasar/Kronos-base"
KRONOS_MODEL_REVISION = "2b554741eca47781b64468546e77fef3e85130e6"
KRONOS_TOKENIZER_ID = "NeoQuasar/Kronos-Tokenizer-base"
KRONOS_TOKENIZER_REVISION = "0e0117387f39004a9016484a186a908917e22426"
MAX_CONTEXT = 512

_IGNORED_PARTS = {".cache", ".git", "__pycache__"}
_ENVIRONMENT_LOCK_KEYS = (
    "python",
    "torch",
    "cuda",
    "cudnn",
    "driver",
    "gpu",
    "compute_capability",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_files(root: str | Path) -> dict[str, str]:
    base = Path(root)
    return {
        path.relative_to(base).as_posix(): _sha256(path)
        for path in sorted(base.rglob("*"))
        if path.is_file()
        and not any(part in _IGNORED_PARTS for part in path.relative_to(base).parts)
        and path.suffix not in {".pyc", ".pyo"}
    }


def _stored_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def build_lock_document(
    *,
    repo_root: str | Path,
    source_root: str | Path,
    model_root: str | Path,
    tokenizer_root: str | Path,
    requirements_path: str | Path,
    environment: dict[str, Any],
    source_commit: str,
    model_created_at: str,
    tokenizer_created_at: str,
    created_at: str,
) -> dict[str, Any]:
    repo = Path(repo_root)
    source = Path(source_root)
    model = Path(model_root)
    tokenizer = Path(tokenizer_root)
    requirements = Path(requirements_path)
    if source_commit != KRONOS_SOURCE_COMMIT:
        raise ValueError(f"Unexpected Kronos source commit: {source_commit}")
    if not environment.get("gpu") or not environment.get("cuda"):
        raise ValueError("A real CUDA GPU environment is required for the model lock")
    return {
        "version": "kronos-model-lock-v1",
        "created_at": created_at,
        "source": {
            "repository": "https://github.com/shiyu-coder/Kronos.git",
            "commit": source_commit,
            "path": _stored_path(source, repo),
            "files": hash_files(source),
        },
        "model": {
            "id": KRONOS_MODEL_ID,
            "revision": KRONOS_MODEL_REVISION,
            "revision_created_at": model_created_at,
            "path": _stored_path(model, repo),
            "files": hash_files(model),
            "max_context": MAX_CONTEXT,
        },
        "tokenizer": {
            "id": KRONOS_TOKENIZER_ID,
            "revision": KRONOS_TOKENIZER_REVISION,
            "revision_created_at": tokenizer_created_at,
            "path": _stored_path(tokenizer, repo),
            "files": hash_files(tokenizer),
        },
        "requirements": {
            "path": _stored_path(requirements, repo),
            "sha256": _sha256(requirements),
        },
        "environment": environment,
        "revision_choice": (
            "Upstream regression pins Kronos-small only; Goal 1 locks the immutable "
            "Kronos-base repository revision required by the PRD."
        ),
    }


def _resolve_path(repo_root: Path, value: str) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else repo_root / candidate


def _validate_file_set(
    label: str, root: Path, expected: dict[str, str], errors: list[str]
) -> None:
    if not root.is_dir():
        errors.append(f"{label} path is missing: {root}")
        return
    actual = hash_files(root)
    for name in sorted(set(expected) | set(actual)):
        if expected.get(name) != actual.get(name):
            errors.append(f"{label}/{name} SHA256 mismatch")


def validate_lock(
    lock: dict[str, Any],
    *,
    repo_root: str | Path,
    current_environment: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    expected_values = {
        ("source", "commit"): KRONOS_SOURCE_COMMIT,
        ("model", "id"): KRONOS_MODEL_ID,
        ("model", "revision"): KRONOS_MODEL_REVISION,
        ("model", "max_context"): MAX_CONTEXT,
        ("tokenizer", "id"): KRONOS_TOKENIZER_ID,
        ("tokenizer", "revision"): KRONOS_TOKENIZER_REVISION,
    }
    for (section, key), expected in expected_values.items():
        if (lock.get(section) or {}).get(key) != expected:
            errors.append(f"{section}.{key} does not match the Goal 1 immutable value")

    repo = Path(repo_root)
    for section in ("source", "model", "tokenizer"):
        item = lock.get(section) or {}
        path_value = item.get("path")
        files = item.get("files")
        if not isinstance(path_value, str) or not isinstance(files, dict):
            errors.append(f"{section} lock is incomplete")
            continue
        _validate_file_set(section, _resolve_path(repo, path_value), files, errors)

    requirements = lock.get("requirements") or {}
    requirement_path = requirements.get("path")
    if isinstance(requirement_path, str):
        resolved = _resolve_path(repo, requirement_path)
        if not resolved.is_file() or _sha256(resolved) != requirements.get("sha256"):
            errors.append("requirements SHA256 mismatch")
    else:
        errors.append("requirements lock is incomplete")

    if current_environment is not None:
        locked_environment = lock.get("environment") or {}
        for key in _ENVIRONMENT_LOCK_KEYS:
            if locked_environment.get(key) != current_environment.get(key):
                errors.append(f"environment.{key} does not match the model lock")
    return errors


def write_lock(path: str | Path, lock: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(
        json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, target)


def _command_output(command: list[str]) -> str:
    return subprocess.run(
        command, check=True, text=True, capture_output=True
    ).stdout.strip()


def collect_environment() -> dict[str, Any]:
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable; CPU fallback is forbidden")
    capability = torch.cuda.get_device_capability(0)
    driver_line = _command_output(
        ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"]
    ).splitlines()[0]
    freeze = _command_output([sys.executable, "-m", "pip", "freeze"]).splitlines()
    return {
        "python": platform.python_version(),
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "cudnn": str(torch.backends.cudnn.version()),
        "driver": driver_line.strip(),
        "gpu": torch.cuda.get_device_name(0),
        "compute_capability": f"{capability[0]}.{capability[1]}",
        "pip_freeze": sorted(freeze, key=str.casefold),
    }


def _git_commit(source_root: Path) -> str:
    return _command_output(["git", "-C", str(source_root), "rev-parse", "HEAD"])


def prepare_and_lock(repo_root: Path) -> dict[str, Any]:
    from huggingface_hub import HfApi, snapshot_download

    source_root = repo_root / "models/kronos/upstream"
    model_root = repo_root / "models/kronos/snapshots/Kronos-base" / KRONOS_MODEL_REVISION
    tokenizer_root = (
        repo_root
        / "models/kronos/snapshots/Kronos-Tokenizer-base"
        / KRONOS_TOKENIZER_REVISION
    )
    for repo_id, revision, local_dir in (
        (KRONOS_MODEL_ID, KRONOS_MODEL_REVISION, model_root),
        (KRONOS_TOKENIZER_ID, KRONOS_TOKENIZER_REVISION, tokenizer_root),
    ):
        snapshot_download(
            repo_id=repo_id,
            revision=revision,
            local_dir=local_dir,
            allow_patterns=["README.md", "config.json", "model.safetensors"],
        )

    api = HfApi()
    model_info = api.model_info(KRONOS_MODEL_ID, revision=KRONOS_MODEL_REVISION)
    tokenizer_info = api.model_info(
        KRONOS_TOKENIZER_ID, revision=KRONOS_TOKENIZER_REVISION
    )
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    lock = build_lock_document(
        repo_root=repo_root,
        source_root=source_root,
        model_root=model_root,
        tokenizer_root=tokenizer_root,
        requirements_path=repo_root / "kronos_runtime/requirements.lock",
        environment=collect_environment(),
        source_commit=_git_commit(source_root),
        model_created_at=model_info.last_modified.isoformat(),
        tokenizer_created_at=tokenizer_info.last_modified.isoformat(),
        created_at=now,
    )
    write_lock(repo_root / "models/kronos/kronos_model_lock.json", lock)
    return lock


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare or verify the Kronos model lock")
    parser.add_argument("command", choices=("prepare", "verify"))
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo_root = args.repo_root.resolve()
    if args.command == "prepare":
        lock = prepare_and_lock(repo_root)
        print(json.dumps({"lock_created": True, "model": lock["model"]["id"]}))
        return 0
    lock_path = repo_root / "models/kronos/kronos_model_lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    errors = validate_lock(
        lock, repo_root=repo_root, current_environment=collect_environment()
    )
    print(json.dumps({"verified": not errors, "errors": errors}, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
