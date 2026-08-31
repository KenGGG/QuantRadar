"""Research-owned SQLAlchemy models; intentionally separate from backtest storage."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class ResearchBase(DeclarativeBase):
    pass


class ResearchReport(ResearchBase):
    __tablename__ = "research_reports"
    __table_args__ = (UniqueConstraint("source", "source_report_id", name="uq_research_report_source_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_report_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    institution: Mapped[str | None] = mapped_column(String(255))
    authors: Mapped[list[str] | None] = mapped_column(JSON)
    publish_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(64))
    industry: Mapped[str | None] = mapped_column(String(255))
    security: Mapped[Any | None] = mapped_column(JSON)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ResearchReportSnapshot(ResearchBase):
    __tablename__ = "research_report_snapshots"
    __table_args__ = (UniqueConstraint("report_id", "target_date", "channel", name="uq_research_snapshot_channel"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("research_reports.id"), nullable=False, index=True)
    target_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    platform_order: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    raw_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class ResearchArtifact(ResearchBase):
    __tablename__ = "research_artifacts"
    report_id: Mapped[int] = mapped_column(ForeignKey("research_reports.id"), primary_key=True)
    pdf_path: Mapped[str | None] = mapped_column(Text)
    pdf_sha256: Mapped[str | None] = mapped_column(String(64))
    pdf_size: Mapped[int | None] = mapped_column(Integer)
    pdf_pages: Mapped[int | None] = mapped_column(Integer)
    platform_pages: Mapped[int | None] = mapped_column(Integer)
    page_count_match: Mapped[bool | None] = mapped_column()
    markdown_path: Mapped[str | None] = mapped_column(Text)
    markdown_sha256: Mapped[str | None] = mapped_column(String(64))
    parser: Mapped[str | None] = mapped_column(String(64))
    parser_version: Mapped[str | None] = mapped_column(String(64))
    parse_quality: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class ResearchArtifactSource(ResearchBase):
    """One auditable source component contributing to canonical Markdown."""
    __tablename__ = "research_artifact_sources"
    __table_args__ = (UniqueConstraint("report_id", "source_kind", "source_sha256", name="uq_research_artifact_source"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("research_artifacts.report_id"), nullable=False, index=True)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    markdown_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    extractor: Mapped[str] = mapped_column(String(64), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_order: Mapped[int] = mapped_column(Integer, nullable=False)
    relation: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN")
    included_in_canonical: Mapped[bool] = mapped_column(nullable=False, default=True)
    relation_reason: Mapped[str] = mapped_column(Text, nullable=False, default="unclassified")


class ResearchStageRun(ResearchBase):
    __tablename__ = "research_stage_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("research_reports.id"), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_hash: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)


class ResearchAnalysis(ResearchBase):
    __tablename__ = "research_analyses"
    __table_args__ = (UniqueConstraint("report_id", "markdown_sha256", "analysis_profile_hash", name="uq_research_analysis_version"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("research_reports.id"), nullable=False, index=True)
    analysis_type: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    markdown_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    analysis_profile_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    output_markdown: Mapped[str | None] = mapped_column(Text)
    research_value: Mapped[str | None] = mapped_column(String(16))
    reproducibility: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    agnes_version: Mapped[str | None] = mapped_column(String(64))
    schema_version: Mapped[str | None] = mapped_column(String(64))
    chunking_version: Mapped[str | None] = mapped_column(String(64))
    analysis_hash: Mapped[str | None] = mapped_column(String(64))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ResearchAnalysisChunk(ResearchBase):
    __tablename__ = "research_analysis_chunks"
    __table_args__ = (UniqueConstraint("report_id", "markdown_sha256", "chunk_index", name="uq_research_analysis_chunk"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("research_reports.id"), nullable=False, index=True)
    markdown_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_id: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    source_start: Mapped[int] = mapped_column(Integer, nullable=False)
    source_end: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)


class ResearchDailyDigest(ResearchBase):
    __tablename__ = "research_daily_digests"
    target_date: Mapped[date] = mapped_column(Date, primary_key=True)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    digest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    digest_version: Mapped[str] = mapped_column(String(64), nullable=False, default="legacy-flat-v1")
    digest_profile_hash: Mapped[str | None] = mapped_column(String(64))
    input_hash: Mapped[str | None] = mapped_column(String(64))
    completeness: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ResearchOutbox(ResearchBase):
    __tablename__ = "research_outbox"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    notification_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    target_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    digest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
