"""Prepare collected PDF reports as versioned MinerU Markdown artifacts."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any

from .config import ResearchSettings
from .download.pdf import PdfDownloader
from .models import ResearchArtifact, ResearchReport
from .parser.mineru import MineruClient
from .parser.quality import assess_markdown
from .storage import ResearchStore


def prepare_report(
    store: ResearchStore,
    settings: ResearchSettings,
    report: ResearchReport,
    *,
    downloader: Any | None = None,
    mineru: Any | None = None,
) -> ResearchArtifact:
    with store._session() as session:
        existing = session.get(ResearchArtifact, report.id)
    if existing is not None and existing.markdown_path and Path(existing.markdown_path).is_file():
        return existing
    attachment = next(
        (item for item in report.source_payload.get("attach", []) if str(item.get("fileUrl") or "").lower().endswith(".pdf")),
        None,
    )
    pdf = (downloader or PdfDownloader(settings.data_dir / "raw" / "pdf")).download(report.source_report_id, attachment)
    if pdf.status != "SUCCESS" or pdf.path is None:
        raise RuntimeError(f"PDF preparation failed: {pdf.error_code or pdf.status}")
    markdown, parser_version = (mineru or MineruClient(settings.mineru_api_url, settings.mineru_timeout_seconds)).parse_pdf(pdf.path)
    digest = sha256(markdown.encode()).hexdigest()
    destination = settings.data_dir / "source_md" / str(report.id) / f"{digest}.md"
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not destination.exists():
        staging = destination.with_suffix(".md.part")
        staging.write_text(markdown, encoding="utf-8")
        staging.replace(destination)
    quality = assess_markdown(markdown)
    return store.save_markdown_artifact(
        report.id,
        destination,
        digest,
        parser="mineru",
        parser_version=parser_version,
        parse_quality={
            "char_count": quality.char_count,
            "replacement_char_ratio": quality.replacement_char_ratio,
            "table_count": quality.table_count,
            "image_count": quality.image_count,
            "status": quality.status,
        },
    )
