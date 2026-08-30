"""Thin, auditable wrapper around the ``url-md`` extractor CLI."""

from __future__ import annotations

from dataclasses import dataclass
from subprocess import CompletedProcess
import subprocess
from typing import Callable, Sequence


class UrlMarkdownError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code


@dataclass(frozen=True)
class UrlMarkdownResult:
    markdown: str
    extractor: str
    extractor_version: str = "url-md"


class UrlMarkdownAdapter:
    def __init__(self, *, binary: str = "url-md", timeout_seconds: int = 60, run: Callable[..., CompletedProcess[str]] = subprocess.run) -> None:
        self.binary = binary
        self.timeout_seconds = timeout_seconds
        self.run = run

    def extract(self, url: str) -> UrlMarkdownResult:
        command: Sequence[str] = [self.binary, "md", url, "--quiet", "--timeout", str(self.timeout_seconds)]
        try:
            completed = self.run(command, capture_output=True, text=True, timeout=self.timeout_seconds, check=False)
        except FileNotFoundError as exc:
            raise UrlMarkdownError("EXTRACTOR_UNAVAILABLE", "url-md is not installed") from exc
        except subprocess.TimeoutExpired as exc:
            raise UrlMarkdownError("NETWORK_TIMEOUT", "url-md timed out") from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "url-md failed").lower()
            if "auth" in detail or "login" in detail:
                code = "AUTH_REQUIRED"
            elif "bot" in detail or "forbidden" in detail or "paywall" in detail:
                code = "ACCESS_DENIED"
            else:
                code = "EXTRACTION_FAILED"
            raise UrlMarkdownError(code, detail[:512])
        markdown = completed.stdout.strip()
        if not markdown:
            raise UrlMarkdownError("EMPTY_MARKDOWN", "url-md returned no Markdown")
        return UrlMarkdownResult(markdown, "url-md-weixin" if "mp.weixin.qq.com/" in url else "url-md-generic")
