"""Operator commands for the isolated Research MVP pipeline."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Sequence

from .collector.qyj import QyjCollector
from .analysis import analyze_markdown
from .config import ResearchSettings
from .llm.agnes import AgnesHttpClient
from .parser.mineru import MineruClient
from .storage import ResearchStore


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quantradar-research")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("health", help="check the configured shared MinerU service")
    collect = commands.add_parser("collect", help="collect QYJ metadata with the persistent headless profile")
    collect.add_argument("--date", type=date.fromisoformat, default=date.today(), help="target date (YYYY-MM-DD)")
    analyze = commands.add_parser("analyze", help="analyze already-published MinerU Markdown only")
    analyze.add_argument("--date", type=date.fromisoformat, required=True, help="target date (YYYY-MM-DD)")
    analyze.add_argument("--limit", type=int, default=30, help="maximum reports to analyze")
    return parser


def run(
    argv: Sequence[str] | None = None,
    *,
    settings: ResearchSettings | None = None,
    mineru_cls=MineruClient,
    collector_cls=QyjCollector,
    agnes_client_cls=AgnesHttpClient,
) -> int:
    args = _parser().parse_args(argv)
    runtime = settings or ResearchSettings.from_env()
    runtime.ensure_directories()

    if args.command == "health":
        response = mineru_cls(runtime.mineru_api_url, runtime.mineru_timeout_seconds).health()
        print(json.dumps({"mineru": response}, ensure_ascii=False, sort_keys=True))
        return 0

    store = ResearchStore(runtime)
    store.create_schema()
    if args.command == "analyze":
        client = agnes_client_cls(runtime.agnes_base_url, runtime.agnes_api_key, runtime.agnes_model)
        analyzed = 0
        for report, artifact in store.list_markdown_reports(args.date, args.limit):
            markdown = Path(artifact.markdown_path).read_text(encoding="utf-8")
            analyze_markdown(store, report.id, markdown, "agnes-v1", runtime.agnes_model, client)
            analyzed += 1
        print(json.dumps({"date": args.date.isoformat(), "analyzed": analyzed}, ensure_ascii=False, sort_keys=True))
        return 0
    result = collector_cls(runtime, store).collect(args.date)
    print(json.dumps({"date": args.date.isoformat(), "counts": {str(channel): len(rows) for channel, rows in result.items()}}, ensure_ascii=False, sort_keys=True))
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
