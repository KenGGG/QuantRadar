"""Snapshot-scoped daily Research digests and idempotent Feishu delivery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
from typing import Callable

import httpx
from sqlalchemy import select

from .config import ResearchSettings
from .analysis import ANALYSIS_PROMPT_VERSION, build_analysis_profile_hash
from .llm.agnes import AgnesClient, AgnesHttpClient
from .models import ResearchDailyDigest, ResearchOutbox, utcnow
from .storage import DigestChannelMember, ResearchStore


DIGEST_VERSION = "yesterday-three-channel-v1"
DIGEST_PROMPT_VERSION = "digest-channel-synthesis-v1"
FORMAL_CHANNELS = (("HOT", "热门研报"), ("STRATEGY", "策略研究"), ("FINANCIAL_ENGINEERING", "金融工程"))


@dataclass(frozen=True)
class DeliveryResult:
    digest_hash: str
    sent: bool
    outbox_status: str


def _canonical_hash(value: object) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _digest_profile_hash(model: str) -> str:
    return _canonical_hash({"version": DIGEST_VERSION, "prompt": DIGEST_PROMPT_VERSION, "model": model})


def _article(member: DigestChannelMember) -> dict:
    assert member.analysis is not None
    output = member.analysis.output_json
    return {"report_id": member.report.id, "platform_order": member.snapshot.platform_order, "title": member.report.title, "institution": member.report.institution, "research_type": output.get("research_type", ""), "one_line_summary": output.get("one_line_summary", ""), "key_points": output.get("key_points", []), "core_conclusion": output.get("core_conclusion", ""), "method_or_logic": output.get("method_or_logic", ""), "risks_or_limitations": output.get("risks_or_limitations", ""), "evidence": output.get("evidence", []), "analysis_hash": member.analysis.analysis_hash}


def _exception(member: DigestChannelMember, channel: str) -> dict[str, str]:
    if member.analysis is not None and member.analysis.status != "SUCCESS":
        return {"title": member.report.title, "channel": channel, "stage": "ANALYZE", "reason": member.analysis.last_error or member.analysis.status}
    if member.latest_stage is not None and member.latest_stage.status.startswith("FAILED"):
        return {"title": member.report.title, "channel": channel, "stage": member.latest_stage.stage, "reason": member.latest_stage.error_message or member.latest_stage.error_code or member.latest_stage.status}
    return {"title": member.report.title, "channel": channel, "stage": "PENDING", "reason": "未找到当前分析版本"}


def _synthesis(client: AgnesClient, channel: str, label: str, articles: list[dict]) -> dict:
    if not articles:
        return {"overall_summary": "该栏目暂无成功分析文章。", "major_themes": [], "important_views": "暂无可综合的成功分析结果。"}
    result = client.complete([
        {"role": "system", "content": "你是中文金融研究编辑。只根据给出的结构化单篇分析，为一个栏目做综合总结；不得编造不存在的主题、共识、分歧或变化。只返回 JSON 对象，字段必须为 overall_summary（字符串）、major_themes（字符串列表）、important_views（字符串）。"},
        {"role": "user", "content": json.dumps({"channel": channel, "channel_label": label, "articles": articles}, ensure_ascii=False, separators=(",", ":"))},
    ])
    if not isinstance(result, dict):
        raise ValueError("Agnes digest synthesis returned non-object JSON")
    summary, themes, views = result.get("overall_summary"), result.get("major_themes"), result.get("important_views")
    if isinstance(views, list) and all(isinstance(item, str) and item.strip() for item in views):
        views = "\n".join(f"- {item.strip()}" for item in views)
    if not isinstance(summary, str) or not summary.strip() or not isinstance(themes, list) or not all(isinstance(item, str) and item.strip() for item in themes) or not isinstance(views, str) or not views.strip():
        raise ValueError("Agnes digest synthesis violates channel contract")
    return {"overall_summary": summary.strip(), "major_themes": [item.strip() for item in themes], "important_views": views.strip()}


def _render_markdown(target_date: date, channels: list[dict], exceptions: list[dict[str, str]]) -> str:
    parts = [f"# QuantRadar 昨日研报摘要 · {target_date.isoformat()}"]
    for numeral, channel in zip(("一", "二", "三"), channels, strict=True):
        parts.extend([f"\n## {numeral}、{channel['channel_label']}", f"\n昨日共采集 {channel['article_count']} 篇，成功分析 {channel['analyzed_count']} 篇，{channel['failed_count']} 篇待处理。", "\n### 栏目概览", channel["overall_summary"], "\n### 主要研究主题"])
        parts.extend(f"{index}. {theme}" for index, theme in enumerate(channel["major_themes"], 1)) or parts.append("暂无。")
        parts.extend(["\n### 重要观点与变化", channel["important_views"], "\n### 文章索引"])
        if not channel["article_index"]:
            parts.append("暂无成功分析文章。")
        for index, article in enumerate(channel["article_index"], 1):
            parts.extend([f"{index}. 《{article['title']}》", f"   - 机构：{article['institution'] or '未披露'}", f"   - 一句话：{article['one_line_summary']}", f"   - 核心观点：{article['core_conclusion']}", f"   - 主要方法/逻辑：{article['method_or_logic']}"])
    parts.append("\n---\n\n## 四、处理异常")
    parts.extend(f"- 《{item['title']}》｜所属栏目：{item['channel']}｜失败阶段：{item['stage']}｜失败原因：{item['reason']}" for item in exceptions) if exceptions else parts.append("- 无")
    return "\n".join(parts) + "\n"


def build_daily_digest(store: ResearchStore, target_date: date, client: AgnesClient, *, analysis_profile_hash: str, model: str) -> ResearchDailyDigest:
    """Build only from Snapshot (target_date, channel) membership, in source order."""
    raw_channels: list[tuple[str, str, list[dict], list[dict[str, str]], list[dict]]] = []
    exceptions: list[dict[str, str]] = []
    for channel, label in FORMAL_CHANNELS:
        members = store.list_digest_channel_members(target_date, channel, analysis_profile_hash=analysis_profile_hash)
        articles = [_article(member) for member in members if member.analysis is not None and member.analysis.status == "SUCCESS"]
        channel_exceptions = [_exception(member, channel) for member in members if member.analysis is None or member.analysis.status != "SUCCESS"]
        fingerprint = [{"report_id": member.report.id, "platform_order": member.snapshot.platform_order, "raw_payload_hash": member.snapshot.raw_payload_hash, "analysis_hash": member.analysis.analysis_hash if member.analysis and member.analysis.status == "SUCCESS" else None, "analysis_status": member.analysis.status if member.analysis else "MISSING"} for member in members]
        raw_channels.append((channel, label, articles, channel_exceptions, fingerprint)); exceptions.extend(channel_exceptions)
    profile_hash = _digest_profile_hash(model)
    input_hash = _canonical_hash({"target_date": target_date.isoformat(), "digest_version": DIGEST_VERSION, "digest_profile_hash": profile_hash, "analysis_profile_hash": analysis_profile_hash, "channels": [{"channel": channel, "members": fingerprint} for channel, _, _, _, fingerprint in raw_channels]})
    with store._session() as session:
        existing = session.get(ResearchDailyDigest, target_date)
        if existing is not None and existing.digest_version == DIGEST_VERSION and existing.digest_profile_hash == profile_hash and existing.input_hash == input_hash:
            return existing
    channels = []
    for channel, label, articles, channel_exceptions, _ in raw_channels:
        synthesis = _synthesis(client, channel, label, articles)
        channels.append({"channel": channel, "channel_label": label, "article_count": len(articles) + len(channel_exceptions), "analyzed_count": len(articles), "failed_count": len(channel_exceptions), "overall_summary": synthesis["overall_summary"], "major_themes": synthesis["major_themes"], "important_views": synthesis["important_views"], "article_index": articles})
    content_json = {"date": target_date.isoformat(), "digest_version": DIGEST_VERSION, "digest_profile_hash": profile_hash, "analysis_profile_hash": analysis_profile_hash, "input_hash": input_hash, "channels": channels, "processing_exceptions": exceptions}
    content_md, digest_hash = _render_markdown(target_date, channels, exceptions), _canonical_hash(content_json)
    with store._session() as session:
        digest = session.get(ResearchDailyDigest, target_date)
        if digest is None:
            digest = ResearchDailyDigest(target_date=target_date, content_md=content_md, content_json=content_json, digest_hash=digest_hash, digest_version=DIGEST_VERSION, digest_profile_hash=profile_hash, input_hash=input_hash, completeness="READY")
            session.add(digest)
        else:
            digest.content_md, digest.content_json, digest.digest_hash = content_md, content_json, digest_hash
            digest.digest_version, digest.digest_profile_hash, digest.input_hash, digest.completeness = DIGEST_VERSION, profile_hash, input_hash, "READY"
        session.commit(); session.refresh(digest)
        return digest


def deliver_daily_digest(
    store: ResearchStore,
    settings: ResearchSettings,
    target_date: date,
    *,
    post: Callable[[str, dict], int] | None = None,
    synthesis_client: AgnesClient | None = None,
) -> DeliveryResult:
    if not settings.feishu_webhook_url:
        raise RuntimeError("QUANTRADAR_FEISHU_WEBHOOK_URL is required")
    client = synthesis_client or AgnesHttpClient(
        settings.agnes_base_url,
        settings.agnes_api_key,
        settings.agnes_model,
        requests_per_minute=settings.agnes_rpm,
    )
    analysis_profile_hash = build_analysis_profile_hash(
        ANALYSIS_PROMPT_VERSION, settings.agnes_model, "agnes-http-v1", "schema-v2", "chunking-v1"
    )
    digest = build_daily_digest(store, target_date, client, analysis_profile_hash=analysis_profile_hash, model=settings.agnes_model)
    text = "\n".join(filter(None, [
        settings.feishu_required_keyword,
        f"QuantRadar 昨日研报摘要 · {target_date.isoformat()}",
        *[f"{item['channel_label']}：采集 {item['article_count']} 篇，成功分析 {item['analyzed_count']} 篇；{item['overall_summary']}" for item in digest.content_json["channels"]],
        f"待处理：{len(digest.content_json['processing_exceptions'])} 篇（详见 WebUI Digest）。" if digest.content_json["processing_exceptions"] else "",
    ]))
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
