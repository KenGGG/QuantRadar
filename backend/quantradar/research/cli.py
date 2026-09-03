"""Operator commands for the isolated Research MVP pipeline."""

from __future__ import annotations

import argparse
import json
import asyncio
from datetime import date
from pathlib import Path
from typing import Sequence

from .collector.qyj import QyjCollector
from .content_sources import build_content_inventory, detect_content_sources
from .analysis import ANALYSIS_PROMPT_VERSION, analyze_markdown, build_analysis_profile_hash
from .config import ResearchSettings
from .delivery import deliver_daily_digest
from .llm.agnes import AgnesHttpClient
from .parser.mineru import MineruClient
from .pipeline import _preparation_input_hash, run_pipeline
from .operations import ResearchRunLock, write_operation_record
from .preparation import prepare_report
from .storage import ResearchStore


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quantradar-research")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("health", help="check the configured shared MinerU service")
    collect = commands.add_parser("collect", help="collect QYJ metadata with the persistent headless profile")
    collect.add_argument("--date", type=date.fromisoformat, default=date.today(), help="target date (YYYY-MM-DD)")
    inventory = commands.add_parser("content-inventory", help="write a redacted source-type inventory for collected snapshots")
    inventory.add_argument("--date", type=date.fromisoformat, required=True, help="target date (YYYY-MM-DD)")
    prepare = commands.add_parser("prepare", help="download collected PDFs and publish MinerU Markdown")
    prepare.add_argument("--date", type=date.fromisoformat, required=True, help="target date (YYYY-MM-DD)")
    prepare.add_argument("--limit", type=int, default=30, help="maximum reports to prepare")
    analyze = commands.add_parser("analyze", help="analyze already-published MinerU Markdown only")
    analyze.add_argument("--date", type=date.fromisoformat, required=True, help="target date (YYYY-MM-DD)")
    analyze.add_argument("--limit", type=int, default=30, help="maximum reports to analyze")
    pipeline = commands.add_parser("pipeline", help="run the resumable collect-to-analysis pipeline")
    pipeline.add_argument("--date", type=date.fromisoformat, required=True, help="target date (YYYY-MM-DD)")
    pipeline.add_argument("--limit", type=int, default=30, help="maximum reports to prepare and analyze")
    deliver = commands.add_parser("deliver", help="build and send the idempotent daily research digest")
    deliver.add_argument("--date", type=date.fromisoformat, required=True, help="target date (YYYY-MM-DD)")
    commands.add_parser("notebooklm-policy-runtime-pass", help="run the frozen NotebookLM runtime acceptance path")
    return parser


def run(
    argv: Sequence[str] | None = None,
    *,
    settings: ResearchSettings | None = None,
    mineru_cls=MineruClient,
    collector_cls=QyjCollector,
    agnes_client_cls=AgnesHttpClient,
    prepare_fn=prepare_report,
    analyze_fn=analyze_markdown,
    pipeline_fn=run_pipeline,
    delivery_fn=deliver_daily_digest,
) -> int:
    args = _parser().parse_args(argv)
    runtime = settings or ResearchSettings.from_env()
    runtime.ensure_directories()

    if args.command == "health":
        response = mineru_cls(runtime.mineru_api_url, runtime.mineru_timeout_seconds).health()
        print(json.dumps({"mineru": response}, ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "pipeline":
        with ResearchRunLock(runtime.data_dir / "runtime" / "research.lock"):
            result = pipeline_fn(runtime, args.date, limit=args.limit)
        write_operation_record(runtime.data_dir, "pipeline", {"date": result.target_date, "collected": result.collected, "prepared": result.prepared, "prepare_failed": result.prepare_failed, "analyzed": result.analyzed, "analyze_failed": result.analyze_failed})
        print(json.dumps({
            "date": result.target_date,
            "collected": result.collected,
            "prepared": result.prepared,
            "prepare_failed": result.prepare_failed,
            "analyzed": result.analyzed,
            "analyze_failed": result.analyze_failed,
        }, ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "notebooklm-policy-runtime-pass":
        from .notebooklm_runtime import RuntimeSettings, run_policy_runtime_pass, runtime_exit_code

        runtime_settings = RuntimeSettings.from_env(runtime.data_dir)
        result = asyncio.run(run_policy_runtime_pass(runtime_settings))
        print(json.dumps(result.as_json(), ensure_ascii=False, sort_keys=True))
        return runtime_exit_code(result)

    store = ResearchStore(runtime)
    store.create_schema()
    if args.command == "content-inventory":
        snapshots = store.list_snapshots(args.date)
        reports = {report.id: report for report in store.list_reports_for_preparation(args.date, limit=max(len(snapshots), 1))}
        rows = [(snapshot.channel, snapshot.report_id, reports[snapshot.report_id].title, reports[snapshot.report_id].source_payload) for snapshot in snapshots if snapshot.report_id in reports]
        inventory = {
            "target_date": args.date.isoformat(),
            "channels": build_content_inventory(rows),
            "reports": [{"channel": channel, "report_id": report_id, "title": title, "sources": [source.kind.value for source in detect_content_sources(payload)]} for channel, report_id, title, payload in rows],
        }
        destination = runtime.data_dir / "acceptance" / f"multiformat-content-inventory-{args.date.isoformat()}.json"
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination.write_text(json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"path": str(destination), "channels": inventory["channels"]}, ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "deliver":
        with ResearchRunLock(runtime.data_dir / "runtime" / "research.lock"):
            result = delivery_fn(store, runtime, args.date)
        write_operation_record(runtime.data_dir, "deliver", {"date": args.date.isoformat(), "digest_hash": result.digest_hash, "sent": result.sent, "outbox_status": result.outbox_status})
        print(json.dumps({"date": args.date.isoformat(), "digest_hash": result.digest_hash, "sent": result.sent, "outbox_status": result.outbox_status}, ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "prepare":
        prepared, failed = 0, 0
        for report in store.list_reports_for_preparation(args.date, args.limit):
            stage = store.begin_stage(report.id, "PREPARE", _preparation_input_hash(report))
            if stage.status == "SUCCESS":
                continue
            try:
                artifact = prepare_fn(store, runtime, report)
                store.finish_stage(stage.id, "SUCCESS", output_hash=getattr(artifact, "markdown_sha256", None))
                prepared += 1
            except Exception as exc:
                store.finish_stage(stage.id, "FAILED", error_code=getattr(exc, "code", type(exc).__name__), error_message=str(exc)[:512])
                failed += 1
        print(json.dumps({"date": args.date.isoformat(), "prepared": prepared, "failed": failed}, ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "analyze":
        client = agnes_client_cls(runtime.agnes_base_url, runtime.agnes_api_key, runtime.agnes_model, requests_per_minute=runtime.agnes_rpm)
        profile_hash = build_analysis_profile_hash(ANALYSIS_PROMPT_VERSION, runtime.agnes_model, "agnes-http-v1", "schema-v2", "chunking-v1")
        analyzed, failed = 0, 0
        for report, artifact in store.list_markdown_reports(args.date, args.limit, profile_hash):
            markdown = Path(artifact.markdown_path).read_text(encoding="utf-8")
            try:
                analyze_fn(store, report.id, markdown, profile_hash, runtime.agnes_model, client)
                analyzed += 1
            except Exception:
                failed += 1
        print(json.dumps({"date": args.date.isoformat(), "analyzed": analyzed, "failed": failed}, ensure_ascii=False, sort_keys=True))
        return 0
    result = collector_cls(runtime, store).collect(args.date)
    print(json.dumps({"date": args.date.isoformat(), "counts": {str(channel): len(rows) for channel, rows in result.items()}}, ensure_ascii=False, sort_keys=True))
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
