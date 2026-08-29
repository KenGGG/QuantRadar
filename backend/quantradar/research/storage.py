"""Transactional persistence for Research-owned tables."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import Engine, create_engine, func, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

from .config import ResearchSettings
from .models import ResearchAnalysis, ResearchAnalysisChunk, ResearchArtifact, ResearchBase, ResearchOutbox, ResearchReport, ResearchReportSnapshot, ResearchStageRun, utcnow


class ResearchStore:
    def __init__(self, settings: ResearchSettings):
        self.settings = settings
        self.engine: Engine = create_engine(settings.database_url, future=True, pool_pre_ping=True)
        self._sessions = sessionmaker(self.engine, expire_on_commit=False, future=True)

    def create_schema(self) -> None:
        ResearchBase.metadata.create_all(self.engine)
        self._upgrade_analysis_schema()

    def _upgrade_analysis_schema(self) -> None:
        """Additive compatibility migration for Research databases created before Agnes v1."""
        inspector = inspect(self.engine)
        if "research_analyses" not in inspector.get_table_names():
            return
        existing = {column["name"] for column in inspector.get_columns("research_analyses")}
        additions = {
            "markdown_sha256": "VARCHAR(64)", "analysis_profile_hash": "VARCHAR(64)",
            "status": "VARCHAR(32) DEFAULT 'PENDING'", "agnes_version": "VARCHAR(64)",
            "schema_version": "VARCHAR(64)", "chunking_version": "VARCHAR(64)",
            "analysis_hash": "VARCHAR(64)", "attempt_count": "INTEGER DEFAULT 0",
            "last_error": "TEXT", "updated_at": "TIMESTAMP" if self.engine.dialect.name == "postgresql" else "DATETIME",
        }
        with self.engine.begin() as connection:
            for name, definition in additions.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE research_analyses ADD COLUMN {name} {definition}"))
            connection.execute(text("UPDATE research_analyses SET markdown_sha256 = input_hash WHERE markdown_sha256 IS NULL"))
            connection.execute(text("UPDATE research_analyses SET analysis_profile_hash = prompt_version WHERE analysis_profile_hash IS NULL"))
            connection.execute(text("UPDATE research_analyses SET status = 'SUCCESS' WHERE status IS NULL"))

    def _session(self) -> Session:
        return self._sessions()

    def upsert_report(self, payload: dict[str, Any]) -> ResearchReport:
        with self._session() as session:
            row = session.scalar(select(ResearchReport).where(ResearchReport.source == payload["source"], ResearchReport.source_report_id == payload["source_report_id"]))
            if row is None:
                row = ResearchReport(**payload)
                session.add(row)
            else:
                for field, value in payload.items():
                    setattr(row, field, value)
            session.commit()
            session.refresh(row)
            return row

    def report_count(self) -> int:
        with self._session() as session:
            return len(session.scalars(select(ResearchReport)).all())

    def list_dates(self) -> list[date]:
        with self._session() as session:
            rows = session.scalars(select(ResearchReport.publish_date).distinct().order_by(ResearchReport.publish_date.desc())).all()
            return list(rows)

    def record_snapshot(self, report_id: int, target_date: date, channel: str, platform_order: int, raw_payload_hash: str) -> ResearchReportSnapshot:
        with self._session() as session:
            row = session.scalar(select(ResearchReportSnapshot).where(ResearchReportSnapshot.report_id == report_id, ResearchReportSnapshot.target_date == target_date, ResearchReportSnapshot.channel == channel))
            if row is None:
                row = ResearchReportSnapshot(report_id=report_id, target_date=target_date, channel=channel, platform_order=platform_order, raw_payload_hash=raw_payload_hash)
                session.add(row)
            else:
                row.platform_order = platform_order
                row.raw_payload_hash = raw_payload_hash
                row.snapshot_at = utcnow()
            session.commit(); session.refresh(row)
            return row

    def list_snapshots(self, target_date: date) -> list[ResearchReportSnapshot]:
        with self._session() as session:
            return list(session.scalars(select(ResearchReportSnapshot).where(ResearchReportSnapshot.target_date == target_date).order_by(ResearchReportSnapshot.channel, ResearchReportSnapshot.platform_order)).all())

    def list_channel_reports(self, target_date: date, channel: str) -> list[dict[str, Any]]:
        """Return safe, presentation-ready report metadata for one collected channel."""
        with self._session() as session:
            rows = session.execute(
                select(ResearchReportSnapshot, ResearchReport)
                .join(ResearchReport, ResearchReport.id == ResearchReportSnapshot.report_id)
                .where(
                    ResearchReportSnapshot.target_date == target_date,
                    ResearchReportSnapshot.channel == channel,
                )
                .order_by(ResearchReportSnapshot.platform_order)
            ).all()
            stage_rows = session.scalars(
                select(ResearchStageRun).order_by(ResearchStageRun.report_id, ResearchStageRun.id.desc())
            ).all()
            latest_status: dict[int, str] = {}
            for row in stage_rows:
                latest_status.setdefault(row.report_id, row.status)

            return [
                {
                    "id": report.id,
                    "title": report.title,
                    "institution": report.institution,
                    "publish_date": report.publish_date,
                    "content_type": report.content_type,
                    "channel": snapshot.channel,
                    "platform_order": snapshot.platform_order,
                    "status": latest_status.get(
                        report.id,
                        "PENDING" if report.content_type == "pdf" else "UNSUPPORTED",
                    ),
                }
                for snapshot, report in rows
            ]

    def channel_counts(self, target_date: date) -> dict[str, int]:
        with self._session() as session:
            rows = session.execute(
                select(ResearchReportSnapshot.channel, func.count())
                .where(ResearchReportSnapshot.target_date == target_date)
                .group_by(ResearchReportSnapshot.channel)
            ).all()
            return {str(channel): count for channel, count in rows}

    def begin_stage(self, report_id: int, stage: str, input_hash: str) -> ResearchStageRun:
        with self._session() as session:
            row = session.scalar(select(ResearchStageRun).where(ResearchStageRun.report_id == report_id, ResearchStageRun.stage == stage, ResearchStageRun.input_hash == input_hash).order_by(ResearchStageRun.id.desc()))
            if row is not None and row.status == "SUCCESS":
                return row
            attempt = (row.attempt + 1) if row is not None else 1
            row = ResearchStageRun(report_id=report_id, stage=stage, status="RUNNING", attempt=attempt, input_hash=input_hash)
            session.add(row); session.commit(); session.refresh(row)
            return row

    def finish_stage(self, stage_run_id: int, status: str, *, output_hash: str | None = None, error_code: str | None = None, error_message: str | None = None) -> ResearchStageRun:
        with self._session() as session:
            row = session.get(ResearchStageRun, stage_run_id)
            if row is None:
                raise KeyError(stage_run_id)
            row.status, row.output_hash, row.error_code, row.error_message, row.finished_at = status, output_hash, error_code, error_message, utcnow()
            session.commit(); session.refresh(row)
            return row

    def reserve_outbox(self, notification_key: str, target_date: date, digest_hash: str, payload_hash: str) -> ResearchOutbox:
        with self._session() as session:
            row = session.scalar(select(ResearchOutbox).where(ResearchOutbox.notification_key == notification_key))
            if row is None:
                row = ResearchOutbox(notification_key=notification_key, target_date=target_date, digest_hash=digest_hash, payload_hash=payload_hash)
                session.add(row); session.commit(); session.refresh(row)
            return row

    def outbox_count(self) -> int:
        with self._session() as session:
            return len(session.scalars(select(ResearchOutbox)).all())

    def save_analysis(self, report_id: int, markdown_sha256: str, prompt_version: str, model: str, output_json: dict[str, Any]) -> ResearchAnalysis:
        """Persist one reproducible analysis; identical source and prompt are reused."""
        with self._session() as session:
            row = session.scalar(select(ResearchAnalysis).where(
                ResearchAnalysis.report_id == report_id,
                ResearchAnalysis.markdown_sha256 == markdown_sha256,
                ResearchAnalysis.analysis_profile_hash == prompt_version,
            ))
            if row is None:
                row = ResearchAnalysis(
                    report_id=report_id,
                    analysis_type=str(output_json.get("research_type", "MARKET")),
                    model=model,
                    prompt_version=prompt_version,
                    markdown_sha256=markdown_sha256,
                    analysis_profile_hash=prompt_version,
                    input_hash=markdown_sha256,
                    output_json=output_json,
                    status="SUCCESS",
                )
                session.add(row)
            else:
                row.analysis_type = str(output_json.get("research_type", "MARKET"))
                row.model = model
                row.output_json = output_json
                row.status = "SUCCESS"
                row.last_error = None
                row.attempt_count += 1
            session.commit(); session.refresh(row)
            return row

    def analysis_count(self) -> int:
        with self._session() as session:
            return len(session.scalars(select(ResearchAnalysis)).all())

    def list_markdown_reports(self, target_date: date, limit: int) -> list[tuple[ResearchReport, ResearchArtifact]]:
        with self._session() as session:
            return list(session.execute(
                select(ResearchReport, ResearchArtifact)
                .join(ResearchArtifact, ResearchArtifact.report_id == ResearchReport.id)
                .where(ResearchReport.publish_date == target_date, ResearchArtifact.markdown_path.is_not(None))
                .order_by(ResearchReport.id).limit(limit)
            ).all())

    def save_analysis_chunks(self, report_id: int, markdown_sha256: str, chunks) -> None:
        with self._session() as session:
            for chunk in chunks:
                row = session.scalar(select(ResearchAnalysisChunk).where(ResearchAnalysisChunk.report_id == report_id, ResearchAnalysisChunk.markdown_sha256 == markdown_sha256, ResearchAnalysisChunk.chunk_index == chunk.chunk_index))
                if row is None:
                    session.add(ResearchAnalysisChunk(report_id=report_id, markdown_sha256=markdown_sha256, chunk_id=chunk.chunk_id, chunk_index=chunk.chunk_index, source_start=chunk.source_start, source_end=chunk.source_end, chunk_sha256=chunk.chunk_sha256, text=chunk.text))
            session.commit()

    def list_analysis_chunks(self, report_id: int, markdown_sha256: str) -> list[ResearchAnalysisChunk]:
        with self._session() as session:
            return list(session.scalars(select(ResearchAnalysisChunk).where(ResearchAnalysisChunk.report_id == report_id, ResearchAnalysisChunk.markdown_sha256 == markdown_sha256).order_by(ResearchAnalysisChunk.chunk_index)).all())

    def record_analysis_failure(self, report_id: int, markdown_sha256: str, profile_hash: str, model: str, error: Exception) -> ResearchAnalysis:
        with self._session() as session:
            row = session.scalar(select(ResearchAnalysis).where(ResearchAnalysis.report_id == report_id, ResearchAnalysis.markdown_sha256 == markdown_sha256, ResearchAnalysis.analysis_profile_hash == profile_hash))
            if row is None:
                row = ResearchAnalysis(report_id=report_id, analysis_type="UNKNOWN", model=model, prompt_version=profile_hash, markdown_sha256=markdown_sha256, analysis_profile_hash=profile_hash, input_hash=markdown_sha256, output_json={}, status="FAILED_RETRYABLE", attempt_count=1, last_error=type(error).__name__)
                session.add(row)
            else:
                row.status, row.attempt_count, row.last_error = "FAILED_RETRYABLE", row.attempt_count + 1, type(error).__name__
            session.commit(); session.refresh(row)
            return row

    def latest_analysis(self, report_id: int, profile_hash: str) -> ResearchAnalysis:
        with self._session() as session:
            row = session.scalar(select(ResearchAnalysis).where(ResearchAnalysis.report_id == report_id, ResearchAnalysis.analysis_profile_hash == profile_hash).order_by(ResearchAnalysis.id.desc()))
            if row is None: raise KeyError(report_id)
            return row
