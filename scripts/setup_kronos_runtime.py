#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Callable

from quantradar.kronos.runtime.contracts import KRONOS_SOURCE_COMMIT

KRONOS_REPOSITORY = "https://github.com/shiyu-coder/Kronos.git"


def setup_runtime(
    repo_root: str | Path,
    *,
    run: Callable = subprocess.run,
    bootstrap_python: str = sys.executable,
) -> None:
    root = Path(repo_root).resolve()
    environment = root / ".venv-kronos"
    runtime_python = environment / "bin/python"
    requirements = root / "kronos_runtime/requirements.lock"
    source = root / "models/kronos/upstream"

    if not runtime_python.is_file():
        run(
            [bootstrap_python, "-m", "venv", str(environment)],
            check=True,
        )
    run(
        [
            str(runtime_python),
            "-m",
            "pip",
            "install",
            "--requirement",
            str(requirements),
        ],
        check=True,
    )
    source.parent.mkdir(parents=True, exist_ok=True)
    if not (source / ".git").is_dir():
        run(
            [
                "git",
                "clone",
                "--filter=blob:none",
                "--no-checkout",
                KRONOS_REPOSITORY,
                str(source),
            ],
            check=True,
        )
    else:
        run(
            ["git", "-C", str(source), "fetch", "origin", KRONOS_SOURCE_COMMIT],
            check=True,
        )
    run(
        [
            "git",
            "-C",
            str(source),
            "checkout",
            "--detach",
            KRONOS_SOURCE_COMMIT,
        ],
        check=True,
    )
    run(
        [
            str(runtime_python),
            str(root / "kronos_runtime/model_lock.py"),
            "prepare",
            "--repo-root",
            str(root),
        ],
        check=True,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create the isolated, immutable Kronos-base CUDA runtime"
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    setup_runtime(args.repo_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
