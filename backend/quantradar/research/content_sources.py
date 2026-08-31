"""Detect the auditable body sources present in QYJ metadata."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from collections import Counter, defaultdict


class ContentKind(StrEnum):
    PDF = "PDF"
    WEIXIN = "WEIXIN"
    HTML_EMBEDDED = "HTML_EMBEDDED"
    HTML_URL = "HTML_URL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ContentSource:
    kind: ContentKind
    url: str | None = None
    html: str | None = None
    field_path: str | None = None


def detect_content_sources(payload: dict[str, Any]) -> list[ContentSource]:
    """Classify concrete report-body sources without treating QYJ navigation as body."""
    sources: list[ContentSource] = []
    for index, attachment in enumerate(payload.get("attach") or []):
        if not isinstance(attachment, dict):
            continue
        url = str(attachment.get("fileUrl") or "")
        if url.lower().split("?", 1)[0].endswith(".pdf") or attachment.get("icon") == "pdf":
            sources.append(ContentSource(ContentKind.PDF, url=url, field_path=f"attach[{index}].fileUrl"))
    embedded_html = payload.get("abstract")
    if isinstance(embedded_html, str) and embedded_html.strip():
        sources.append(ContentSource(ContentKind.HTML_EMBEDDED, html=embedded_html, field_path="abstract"))
    for key, value in payload.items():
        if not isinstance(value, str) or not value.startswith(("https://", "http://")):
            continue
        if key in {"linkUrl", "pcContentLink", "appContentLink"}:
            continue
        if value.lower().split("?", 1)[0].endswith(".pdf"):
            continue
        kind = ContentKind.WEIXIN if "mp.weixin.qq.com/" in value else ContentKind.HTML_URL
        sources.append(ContentSource(kind, url=value, field_path=key))
    return sources or [ContentSource(ContentKind.UNKNOWN)]


def build_content_inventory(rows: list[tuple[str, int, str, dict[str, Any]]]) -> dict[str, dict[str, int]]:
    """Summarize source types without retaining raw metadata or credentials."""
    inventories: dict[str, Counter[str]] = defaultdict(Counter)
    for channel, _report_id, _title, payload in rows:
        kinds = {source.kind.value for source in detect_content_sources(payload)}
        count = inventories[channel]
        count["upstream_count"] += 1
        count["classified_report_count"] += 1
        for kind in kinds:
            count[kind] += 1
        if len(kinds - {ContentKind.UNKNOWN.value}) > 1:
            count["MULTI_SOURCE"] += 1
        if kinds == {ContentKind.UNKNOWN.value}:
            count["NO_CONTENT"] += 1
    return {channel: dict(count) for channel, count in inventories.items()}
