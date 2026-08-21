#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

from quantradar.config import load_investment_data_config
from quantradar.kronos.runtime.orchestrator import run_gpu_smoke
from quantradar.providers.investment_data.provider import InvestmentDataProvider

DEFAULT_OUTPUT = Path("reports/kronos/runtime_smoke")


def execute_gpu_smoke_cli(
    provider,
    repo_root: Path,
    output_dir: Path,
    *,
    smoke_runner: Callable = run_gpu_smoke,
) -> int:
    outcome = smoke_runner(
        provider,
        repo_root=repo_root,
        output_dir=output_dir,
    )
    gate = outcome["gate"]
    print(
        json.dumps(
            {
                "output_dir": outcome["output_dir"],
                "runtime_ready": gate["runtime_ready"],
                "status": gate["status"],
                "completion_marker": gate["completion_marker"],
                "reasons": gate["reasons"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if gate["runtime_ready"] else 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the immutable Kronos-base Goal 1 real GPU smoke"
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    provider = InvestmentDataProvider(load_investment_data_config())
    try:
        return execute_gpu_smoke_cli(
            provider, args.repo_root.resolve(), args.output
        )
    finally:
        provider.connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
