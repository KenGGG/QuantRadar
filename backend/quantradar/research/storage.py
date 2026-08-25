"""Transactional persistence for Research-owned tables."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from .config import ResearchSettings
from .models import ResearchBase, ResearchOutbox, ResearchReport, ResearchReportSnapshot, ResearchStageRun, utcnow


class ResearchStore:
    def __init__(self, settings: ResearchSettings):
        self.settings = settings
        self.engine: Engine = create_engine(settings.database_url, future=True, pool_pre_ping=True)
        self._sessions = sessionmaker(self.engine, expire_on_commit=False, future=True)

    def create_schema(self) -> None:
        ResearchBase.metadata.create_all(self.engine)

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
