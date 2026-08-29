"""Headless Enterprise Warning Center (QYJ) report metadata collector."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable

from ..config import ResearchSettings
from ..storage import ResearchStore


class Channel(StrEnum):
    HOT = "HOT"
    STRATEGY = "STRATEGY"
    FINANCIAL_ENGINEERING = "FINANCIAL_ENGINEERING"


CHANNEL_PARAMS = {
    Channel.HOT: {"hotReport": "1", "secondReportType": ""},
    Channel.STRATEGY: {"secondReportType": "10301,10302,10303"},
    Channel.FINANCIAL_ENGINEERING: {"secondReportType": "10202,10203"},
}


class AuthState(StrEnum):
    AUTH_OK = "AUTH_OK"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    CAPTCHA_REQUIRED = "CAPTCHA_REQUIRED"
    AUTH_UNKNOWN = "AUTH_UNKNOWN"


class QyjAuthenticationError(RuntimeError):
    def __init__(self, state: AuthState):
        super().__init__(state)
        self.code = str(state)


@dataclass(frozen=True)
class NormalizedReport:
    report: dict[str, Any]
    channel: Channel
    platform_order: int
    raw_payload_hash: str
    attachment: dict[str, Any] | None


FetchPage = Callable[[Channel, date, int, int], dict[str, Any]]


def _as_date(raw: str | None, target_date: date) -> date:
    if not raw:
        return target_date
    if re.fullmatch(r"\d{2}-\d{2}", raw):
        return date(target_date.year, int(raw[:2]), int(raw[3:]))
    return date.fromisoformat(raw)


def normalize_report(payload: dict[str, Any], channel: Channel, platform_order: int, target_date: date) -> NormalizedReport:
    source_id = str(payload.get("id") or "").upper()
    if not re.fullmatch(r"[0-9A-F]{32}", source_id):
        raise ValueError("QYJ source_report_id must be a 32-character hexadecimal ID")
    attachments = payload.get("attach") or []
    attachment = next((item for item in attachments if str(item.get("fileUrl") or "").lower().endswith(".pdf")), None)
    authors = [str(item.get("authorName")) for item in payload.get("author") or [] if item.get("authorName")]
    report = {
        "source": "qyj",
        "source_report_id": source_id,
        "title": str(payload.get("title") or "").strip() or source_id,
        "institution": payload.get("institutionName") or payload.get("institution"),
        "authors": authors or None,
        "publish_date": _as_date(payload.get("publishDate"), target_date),
        "category": payload.get("reportType"),
        "industry": payload.get("industry"),
        "security": payload.get("security"),
        "content_type": "pdf" if attachment else "non_pdf",
        "source_payload": payload,
    }
    raw_payload_hash = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return NormalizedReport(report, channel, platform_order, raw_payload_hash, attachment)


class QyjCollector:
    def __init__(self, settings: ResearchSettings | None = None, store: ResearchStore | None = None, *, fetch_page: FetchPage | None = None, auth_probe: Callable[[], AuthState] | None = None, page_size: int = 50):
        self.settings, self.store, self.fetch_page, self.auth_probe, self.page_size = settings, store, fetch_page, auth_probe, page_size

    def require_authenticated(self) -> None:
        state = self.auth_probe() if self.auth_probe else AuthState.AUTH_OK
        if state != AuthState.AUTH_OK:
            raise QyjAuthenticationError(state)

    def collect_channel(self, channel: Channel, target_date: date) -> list[NormalizedReport]:
        self.require_authenticated()
        fetch = self.fetch_page or self._browser_fetch_page
        offset, total, seen, results = 0, None, set(), []
        while total is None or offset < total:
            payload = fetch(channel, target_date, offset, self.page_size)
            total = int(payload.get("total") or 0)
            rows = list((payload.get("data") or {}).get("list") or [])
            if not rows:
                break
            for index, row in enumerate(rows, start=offset + 1):
                normalized = normalize_report(row, channel, index, target_date)
                if normalized.report["source_report_id"] not in seen:
                    seen.add(normalized.report["source_report_id"])
                    results.append(normalized)
            offset += self.page_size
        return results

    def collect(self, target_date: date) -> dict[Channel, list[NormalizedReport]]:
        if self.store is None:
            raise RuntimeError("ResearchStore is required to persist a collection")
        result = {channel: self.collect_channel(channel, target_date) for channel in Channel}
        for channel, reports in result.items():
            self._persist_channel(target_date, channel, reports)
        return result

    def _persist_channel(self, target_date: date, channel: Channel, reports: list[NormalizedReport]) -> None:
        assert self.settings and self.store
        raw_dir = self.settings.data_dir / "raw" / "metadata" / f"{target_date:%Y/%m/%d}"
        raw_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        snapshot_path = raw_dir / f"qyj-{channel.value.lower()}.json"
        snapshot_path.write_text(json.dumps([item.report["source_payload"] for item in reports], ensure_ascii=False), encoding="utf-8")
        for item in reports:
            report = self.store.upsert_report(item.report)
            self.store.record_snapshot(report.id, target_date, channel.value, item.platform_order, item.raw_payload_hash)

    @staticmethod
    def _submit_saved_browser_login(page: Any) -> bool:
        """Let Chrome autofill its own saved QYJ credential and submit it.

        Credentials remain inside the persistent Chrome profile: this method never
        reads field values or accesses the password store.
        """
        page.locator("#username").click()
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")
        page.wait_for_timeout(250)
        submit = page.locator("button[type='submit']")
        if not submit.is_enabled():
            return False
        submit.click(no_wait_after=True)
        page.wait_for_timeout(2_000)
        return True

    def _browser_fetch_page(self, channel: Channel, target_date: date, offset: int, size: int) -> dict[str, Any]:
        if self.settings is None:
            raise RuntimeError("ResearchSettings is required for live QYJ collection")
        from playwright.sync_api import sync_playwright

        captured: dict[str, str] = {}
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(self.settings.qyj_profile_dir),
                executable_path="/usr/bin/google-chrome",
                headless=True,
                ignore_default_args=["--enable-automation"],
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://www.qyyjt.cn/report/research", wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(2_000)
            text = page.locator("body").inner_text()
            if "登录" in text and "研究报告" not in text:
                submitted = self._submit_saved_browser_login(page)
                if not submitted:
                    context.close()
                    raise QyjAuthenticationError(AuthState.LOGIN_REQUIRED)
                text = page.locator("body").inner_text()
                if "登录" in text and "研究报告" not in text:
                    context.close()
                    raise QyjAuthenticationError(AuthState.LOGIN_REQUIRED)
            def capture(request):
                if "searchReportNew.action" in request.url and not captured:
                    captured.update(request.headers)
            page.on("request", capture)
            page.reload(wait_until="domcontentloaded"); page.wait_for_timeout(2_000)
            allowed = {key: captured[key] for key in ("accept", "client", "content-type", "pcuss", "system", "system1", "terminal", "user", "ver", "x-request-id", "x-request-url") if key in captured}
            params = {"sortKey": "", "sortType": "", "hotThemeCode": "", "depthOnly": "0", "includeNoAccess": "1", "includeWx": "1", "size": str(size), "from": str(offset), "system": "web", "publishDate": f"[{target_date.isoformat()},{target_date.isoformat()}", **CHANNEL_PARAMS[channel]}
            response = page.evaluate("""async ({params, headers}) => { const r = await fetch('/finchinaAPP/searchReportNew.action', {method: 'POST', headers, credentials: 'include', body: new URLSearchParams(params)}); return await r.json(); }""", {"params": params, "headers": allowed})
            context.close()
            return response
