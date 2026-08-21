#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from quantradar.config import load_investment_data_config
from quantradar.kronos.data_audit.runner import run_data_audit
from quantradar.providers.investment_data.connection import InvestmentDataConnection
from quantradar.providers.investment_data.provider import InvestmentDataProvider


DEFAULT_OUTPUT = Path("reports/kronos/data_audit")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the read-only Kronos Goal 0 data fact audit."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"report directory (default: {DEFAULT_OUTPUT})",
    )
    return parser


def execute_audit_cli(
    connection,
    provider,
    output_dir: Path,
    *,
    audit_runner=run_data_audit,
) -> int:
    result = audit_runner(connection, provider, output_dir)
    gates = result["gates"]
    summary = {
        "output_dir": result["output_dir"],
        "signal_research_ready": gates["signal_research_ready"],
        "formal_backtest_ready": gates["formal_backtest_ready"],
        "real_assist_data_ready": gates["real_assist_data_ready"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_investment_data_config()
    connection = InvestmentDataConnection(config)
    provider = InvestmentDataProvider(config)
    try:
        return execute_audit_cli(connection, provider, args.output)
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
