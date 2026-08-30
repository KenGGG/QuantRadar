"""Resumable collect → prepare → analyze runner for the Research MVP."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .analysis import ANALYSIS_PROMPT_VERSION, analyze_markdown, build_analysis_profile_hash
from .collector.qyj import QyjCollector
from .config import ResearchSettings
from .llm.agnes import AgnesHttpClient
from .models import ResearchArtifact, ResearchReport
from .preparation import prepare_report
from .storage import ResearchStore


@dataclass(frozen=True)
class PipelineResult:
    target_date: str
    collected: int
    prepared: int
    prepare_failed: int
    analyzed: int
    analyze_failed: int


def _preparation_input_hash(report: ResearchReport) -> str:
    payload = {"source_report_id": report.source_report_id, "source_payload": report.source_payload, "canonical_profile": "containment-v2"}
    return sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _artifact(store: ResearchStore, report_id: int) -> ResearchArtifact | None:
    with store._session() as session:
        return session.get(ResearchArtifact, report_id)


def run_pipeline(
    settings: ResearchSettings,
    target_date,
    *,
    limit: int = 30,
    store: ResearchStore | None = None,
    collector_cls=QyjCollector,
    prepare_fn=prepare_report,
    analyze_fn=analyze_markdown,
    agnes_client_cls=AgnesHttpClient,
) -> PipelineResult:
    """Run only the completed intake stages; successful report stages are reused."""
    runtime_store = store or ResearchStore(settings)
    runtime_store.create_schema()
    collected = collector_cls(settings, runtime_store).collect(target_date)
    collected_count = sum(len(rows) for rows in collected.values())
    profile_hash = build_analysis_profile_hash(ANALYSIS_PROMPT_VERSION, settings.agnes_model, "agnes-http-v1", "schema-v2", "chunking-v1")
    client = agnes_client_cls(settings.agnes_base_url, settings.agnes_api_key, settings.agnes_model, requests_per_minute=settings.agnes_rpm)
    prepared = prepare_failed = analyzed = analyze_failed = 0
    for report in runtime_store.list_reports_for_preparation(target_date, limit):
        prepare_stage = runtime_store.begin_stage(report.id, "PREPARE", _preparation_input_hash(report))
        artifact = _artifact(runtime_store, report.id)
        if prepare_stage.status != "SUCCESS" or artifact is None or not artifact.markdown_path or not Path(artifact.markdown_path).is_file():
            try:
                artifact = prepare_fn(runtime_store, settings, report)
                runtime_store.finish_stage(prepare_stage.id, "SUCCESS", output_hash=artifact.markdown_sha256)
                prepared += 1
            except Exception as exc:
                runtime_store.finish_stage(prepare_stage.id, "FAILED", error_code=type(exc).__name__, error_message=str(exc)[:512])
                prepare_failed += 1
                continue
        if artifact is None or not artifact.markdown_path or not artifact.markdown_sha256:
            prepare_failed += 1
            continue
        analysis_input_hash = sha256(f"{artifact.markdown_sha256}:{profile_hash}".encode()).hexdigest()
        analyze_stage = runtime_store.begin_stage(report.id, "ANALYZE", analysis_input_hash)
        if analyze_stage.status == "SUCCESS":
            continue
        try:
            analyze_fn(runtime_store, report.id, Path(artifact.markdown_path).read_text(encoding="utf-8"), profile_hash, settings.agnes_model, client)
            runtime_store.finish_stage(analyze_stage.id, "SUCCESS")
            analyzed += 1
        except Exception as exc:
            runtime_store.finish_stage(analyze_stage.id, "FAILED", error_code=type(exc).__name__, error_message=str(exc)[:512])
            analyze_failed += 1
    return PipelineResult(target_date.isoformat(), collected_count, prepared, prepare_failed, analyzed, analyze_failed)
