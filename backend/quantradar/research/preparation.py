"""Prepare collected PDF reports as versioned MinerU Markdown artifacts."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any
import re

from bs4 import BeautifulSoup

from .config import ResearchSettings
from .content_sources import ContentKind, detect_content_sources
from .download.pdf import PdfDownloader
from .models import ResearchArtifact, ResearchReport
from .parser.mineru import MineruClient
from .parser.quality import assess_markdown
from .qyj_html import QyjHtmlAdapter
from .storage import ResearchStore
from .url_markdown import UrlMarkdownAdapter


def _normalized_text(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]", "", value).lower()


def _classify_components(components: list[dict[str, Any]]) -> None:
    """Use only deterministic containment for PDF/HTML duplicate decisions."""
    for component in components:
        component.update(relation="UNKNOWN", included_in_canonical=True, relation_reason="no deterministic duplicate evidence")
    pdf = next((component for component in components if component["source_kind"] == "PDF"), None)
    if pdf is None:
        return
    pdf.update(relation="PRIMARY", included_in_canonical=True, relation_reason="PDF is the deterministic primary source")
    normalized_pdf = _normalized_text(pdf["body"])
    for component in components:
        if component is pdf or component["source_kind"] != "HTML_EMBEDDED":
            continue
        normalized_html = _normalized_text(component["body"])
        if normalized_html and normalized_html in normalized_pdf:
            component.update(relation="DUPLICATE", included_in_canonical=False, relation_reason="normalized HTML text is contained in PDF text")
        else:
            component.update(relation="SUPPLEMENTARY", included_in_canonical=True, relation_reason="no deterministic containment; preserved conservatively")


def prepare_report(
    store: ResearchStore,
    settings: ResearchSettings,
    report: ResearchReport,
    *,
    downloader: Any | None = None,
    mineru: Any | None = None,
    url_markdown: Any | None = None,
    qyj_html: Any | None = None,
) -> ResearchArtifact:
    sources = detect_content_sources(report.source_payload)
    embedded = next((source for source in sources if source.kind is ContentKind.HTML_EMBEDDED), None)
    expected_source_sha256 = sha256(embedded.html.encode()).hexdigest() if embedded is not None and embedded.html is not None else None
    with store._session() as session:
        existing = session.get(ResearchArtifact, report.id)
    if (
        existing is not None
        and existing.markdown_path
        and Path(existing.markdown_path).is_file()
        and (expected_source_sha256 is None or (existing.parse_quality or {}).get("source_sha256") == expected_source_sha256)
        and (existing.parse_quality or {}).get("relation_profile") == "containment-v2"
    ):
        return existing
    components: list[dict[str, Any]] = []
    source_failures: list[str] = []
    for source in sources:
        if source.kind is ContentKind.PDF:
            attachment = next((item for item in report.source_payload.get("attach", []) if item.get("fileUrl") == source.url), None)
            pdf = (downloader or PdfDownloader(settings.data_dir / "raw" / "pdf")).download(report.source_report_id, attachment)
            if pdf.status != "SUCCESS" or pdf.path is None:
                source_failures.append(f"PDF:{pdf.error_code or pdf.status}")
                continue
            body, version = (mineru or MineruClient(settings.mineru_api_url, settings.mineru_timeout_seconds)).parse_pdf(pdf.path)
            components.append({"source_kind": "PDF", "source_url": source.url, "source_sha256": sha256(pdf.path.read_bytes()).hexdigest(), "body": body, "extractor": "mineru", "extractor_version": version})
        elif source.kind is ContentKind.HTML_EMBEDDED and source.html is not None:
            components.append({"source_kind": "HTML_EMBEDDED", "source_url": None, "source_sha256": sha256(source.html.encode()).hexdigest(), "body": BeautifulSoup(source.html, "html.parser").get_text("\n", strip=True), "extractor": "qyj-html", "extractor_version": "beautifulsoup4"})
        elif source.kind in {ContentKind.WEIXIN, ContentKind.HTML_URL} and source.url is not None:
            extracted = (
                (url_markdown or UrlMarkdownAdapter()).extract(source.url)
                if "mp.weixin.qq.com/" in source.url or source.kind is ContentKind.HTML_URL
                else (qyj_html or QyjHtmlAdapter(settings)).extract(source.url)
            )
            components.append({"source_kind": source.kind.value, "source_url": source.url, "source_sha256": sha256(extracted.markdown.encode()).hexdigest(), "body": extracted.markdown, "extractor": extracted.extractor, "extractor_version": extracted.extractor_version})
    if not components:
        detail = ", ".join(source_failures) if source_failures else sources[0].kind.value
        raise RuntimeError(f"Content preparation failed: {detail}")
    _classify_components(components)
    parser = components[0]["extractor"] if len(components) == 1 else "canonical-merge"
    parser_version = components[0]["extractor_version"] if len(components) == 1 else "v1"
    source_kind = components[0]["source_kind"].lower() if len(components) == 1 else "mixed"
    source_sha256 = sha256("".join(component["source_sha256"] for component in components).encode()).hexdigest()
    included_components = [component for component in components if component["included_in_canonical"]]
    body = included_components[0]["body"] if len(included_components) == 1 else "\n\n".join(f"# Source {index} — {component['source_kind']}\n\n{component['body']}" for index, component in enumerate(included_components, start=1))
    channels = [snapshot.channel for snapshot in store.list_snapshots(report.publish_date) if snapshot.report_id == report.id]
    markdown = "\n".join([
        "---",
        f"report_id: {report.id}",
        f"source_report_id: {report.source_report_id}",
        f"source_kind: {source_kind}",
        f"title: {report.title}",
        f"publish_date: {report.publish_date.isoformat()}",
        "channel_membership:",
        *[f"  - {channel}" for channel in channels],
        f"source_sha256: {source_sha256}",
        f"extractor: {parser}",
        f"extractor_version: {parser_version}",
        "---",
        "",
        body,
    ])
    digest = sha256(markdown.encode()).hexdigest()
    quality = assess_markdown(markdown)
    if quality.status != "PARSE_OK":
        raise RuntimeError(f"Markdown quality failed: {quality.status}")
    destination = settings.data_dir / "source_md" / str(report.id) / f"{digest}.md"
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not destination.exists():
        staging = destination.with_suffix(".md.part")
        staging.write_text(markdown, encoding="utf-8")
        staging.replace(destination)
    artifact = store.save_markdown_artifact(
        report.id,
        destination,
        digest,
        parser=parser,
        parser_version=parser_version,
        parse_quality={
            "char_count": quality.char_count,
            "replacement_char_ratio": quality.replacement_char_ratio,
            "table_count": quality.table_count,
            "image_count": quality.image_count,
            "status": quality.status,
            "source_kind": source_kind,
            "source_sha256": source_sha256,
            "relation_profile": "containment-v2",
        },
    )
    store.save_artifact_sources(report.id, [{key: value for key, value in component.items() if key != "body"} | {"markdown_sha256": sha256(component["body"].encode()).hexdigest(), "source_order": index} for index, component in enumerate(components, start=1)])
    return artifact
