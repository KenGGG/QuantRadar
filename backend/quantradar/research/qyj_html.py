"""Read a QYJ report detail page through the authorized Chrome profile."""

from __future__ import annotations

from bs4 import BeautifulSoup

from .config import ResearchSettings
from .url_markdown import UrlMarkdownError, UrlMarkdownResult


class QyjHtmlAdapter:
    def __init__(self, settings: ResearchSettings, *, timeout_seconds: int = 60) -> None:
        self.settings = settings
        self.timeout_seconds = timeout_seconds

    def extract(self, url: str) -> UrlMarkdownResult:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(self.settings.qyj_profile_dir), executable_path="/usr/bin/google-chrome",
                headless=True, ignore_default_args=["--enable-automation"],
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_seconds * 1000)
                page.wait_for_timeout(1_000)
                body = page.locator("body").inner_text()
                if "/user/login" in page.url or ("手机扫码登录" in body and "账户密码登录" in body):
                    from .collector.qyj import QyjCollector

                    if QyjCollector._submit_saved_browser_login(page):
                        page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_seconds * 1000)
                        page.wait_for_timeout(1_000)
                        body = page.locator("body").inner_text()
                    if "/user/login" in page.url or ("手机扫码登录" in body and "账户密码登录" in body):
                        raise UrlMarkdownError("AUTH_REQUIRED", "QYJ authenticated browser profile requires login")
                candidates = []
                for selector in ("article", "main", ".report-content", ".detail-content", ".article-content"):
                    candidates.extend(page.locator(selector).all_inner_texts())
                text = max((item.strip() for item in candidates if item.strip()), key=len, default=body.strip())
            finally:
                context.close()
        if not text:
            raise UrlMarkdownError("EMPTY_MARKDOWN", "QYJ report detail contains no readable body")
        return UrlMarkdownResult(BeautifulSoup(text, "html.parser").get_text("\n", strip=True), "qyj-authenticated-html", "playwright")
