"""Daily Research digest construction and idempotent Feishu delivery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
from typing import Callable

import httpx
from sqlalchemy import select

from .config import ResearchSettings
from .models import ResearchAnalysis, ResearchDailyDigest, ResearchOutbox, ResearchReport, utcnow
from .storage import ResearchStore


@dataclass(frozen=True)
class DeliveryResult:
    digest_hash: str
    sent: bool
    outbox_status: str


def _digest(store: ResearchStore, target_date: date) -> ResearchDailyDigest:
    with store._session() as session:
        existing = session.get(ResearchDailyDigest, target_date)
        if existing is not None:
            return existing
        rows = list(session.execute(
            select(ResearchReport, ResearchAnalysis)
            .join(ResearchAnalysis, ResearchAnalysis.report_id == ResearchReport.id)
            .where(ResearchReport.publish_date == target_date, ResearchAnalysis.status == "SUCCESS")
            .order_by(ResearchReport.id)
        ).all())
        items = [{"report_id": report.id, "title": report.title, "summary": analysis.output_json.get("one_line_summary", "")} for report, analysis in rows]
        content_md = "# Enterprise Alert Research Digest\n\n" + "\n".join(f"- {item['title']}: {item['summary']}" for item in items)
        content_json = {"date": target_date.isoformat(), "reports": items}
        digest_hash = sha256(json.dumps(content_json, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        digest = ResearchDailyDigest(target_date=target_date, content_md=content_md, content_json=content_json, digest_hash=digest_hash, completeness="READY")
        session.add(digest); session.commit(); session.refresh(digest)
        return digest


def deliver_daily_digest(
    store: ResearchStore,
    settings: ResearchSettings,
    target_date: date,
    *,
    post: Callable[[str, dict], int] | None = None,
) -> DeliveryResult:
    if not settings.feishu_webhook_url:
        raise RuntimeError("QUANTRADAR_FEISHU_WEBHOOK_URL is required")
    digest = _digest(store, target_date)
    text = f"{settings.feishu_required_keyword}\n{digest.content_md}".strip()
    payload = {"msg_type": "text", "content": {"text": text}}
    payload_hash = sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    key = f"research-digest:{target_date.isoformat()}:{digest.digest_hash}"
    outbox = store.reserve_outbox(key, target_date, digest.digest_hash, payload_hash)
    if outbox.status == "SENT":
        return DeliveryResult(digest.digest_hash, False, outbox.status)
    try:
        status = post(settings.feishu_webhook_url, payload) if post else httpx.post(settings.feishu_webhook_url, json=payload, timeout=20).status_code
        if status < 200 or status >= 300:
            raise RuntimeError(f"Feishu HTTP_{status}")
    except Exception as exc:
        with store._session() as session:
            row = session.get(ResearchOutbox, outbox.id)
            row.status, row.attempt, row.last_error = "FAILED", row.attempt + 1, f"{type(exc).__name__}: {exc}"[:512]
            session.commit()
        raise
    with store._session() as session:
        row = session.get(ResearchOutbox, outbox.id)
        row.status, row.attempt, row.sent_at, row.last_error = "SENT", row.attempt + 1, utcnow(), None
        session.commit()
    return DeliveryResult(digest.digest_hash, True, "SENT")
