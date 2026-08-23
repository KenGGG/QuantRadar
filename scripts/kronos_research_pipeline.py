#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

from quantradar.config import load_investment_data_config
from quantradar.kronos.pipeline import run_research_pipeline
from quantradar.kronos.universe_spec import DEFAULT_UNIVERSE, Universe, parse_universe
from quantradar.providers.investment_data.provider import InvestmentDataProvider


def execute_pipeline_cli(
    provider,
    *,
    repo_root: Path,
    artifacts_root: Path,
    runs_dir: Path,
    start: str,
    end: str,
    topk: int,
    universe: Universe = DEFAULT_UNIVERSE,
    pipeline_runner: Callable = run_research_pipeline,
) -> int:
    result = pipeline_runner(
        provider,
        repo_root=repo_root,
        artifacts_root=artifacts_root,
        runs_dir=runs_dir,
        start=start,
        end=end,
        topk=topk,
        universe=universe,
    )
    gate = result["gate"]
    summary = {
        "signal_run_dir": result["signal_run_dir"],
        "backtest_run_dir": result["backtest"]["run_dir"],
        "engineering_ready": gate["engineering_ready"],
        "completion_marker": gate["completion_marker"],
        "universe": universe.value,
        "kronos_signal_research_ready": gate["kronos_signal_research_ready"],
        "research_backtest_ready": gate["research_backtest_ready"],
        "realistic_backtest_ready": gate["realistic_backtest_ready"],
        "real_assist_data_ready": gate["real_assist_data_ready"],
        "csi300_pit_ready": gate["csi300_pit_ready"],
        "formal_backtest_ready": gate["formal_backtest_ready"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if gate.get("completion_marker") == "GOAL2_ENGINEERING_PASS" else 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the research-only Kronos Goal 2 pipeline"
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--artifacts-root", type=Path, default=Path("artifacts/kronos/signals"))
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--topk", type=int, default=20)
    parser.add_argument(
        "--universe",
        default=DEFAULT_UNIVERSE.value,
        type=parse_universe,
        help="signal universe: all_a_liquid (default), csi300_pit, csi500_pit, csi1000_pit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    provider = InvestmentDataProvider(load_investment_data_config())
    try:
        return execute_pipeline_cli(
            provider,
            repo_root=args.repo_root.resolve(),
            artifacts_root=args.artifacts_root.resolve(),
            runs_dir=args.runs_dir.resolve(),
            start=args.start,
            end=args.end,
            topk=args.topk,
            universe=args.universe,
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "engineering_ready": False,
                    "completion_marker": None,
                    "universe": getattr(args, "universe", DEFAULT_UNIVERSE.value),
                    "error": str(exc),
                    "kronos_signal_research_ready": False,
                    "research_backtest_ready": False,
                    "realistic_backtest_ready": False,
                    "real_assist_data_ready": False,
                    "csi300_pit_ready": False,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 2
    finally:
        provider.connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
