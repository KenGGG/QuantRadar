"""Atomic PDF downloader with content validation and SHA-256 identity."""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx


@dataclass(frozen=True)
class PdfArtifactResult:
    status: str
    path: Path | None = None
    sha256: str | None = None
    pages: int | None = None
    platform_pages: int | None = None
    error_code: str | None = None


class PdfDownloader:
    def __init__(self, root: Path, *, fetch: Callable[[str], bytes] | None = None, page_counter: Callable[[Path], int] | None = None):
        self.root, self.fetch, self.page_counter = root, fetch or self._fetch, page_counter or self._pdfinfo_pages

    def download(self, report_id: str, attachment: dict | None) -> PdfArtifactResult:
        url = str((attachment or {}).get("fileUrl") or "")
        if not url.lower().endswith(".pdf"):
            return PdfArtifactResult("UNSUPPORTED", error_code="UNSUPPORTED_CONTENT")
        try:
            data = self.fetch(url)
            if not data.startswith(b"%PDF-"):
                return PdfArtifactResult("FAILED", error_code="PDF_INVALID")
            digest = hashlib.sha256(data).hexdigest()
            destination = self.root / f"{report_id}-{digest}.pdf"
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if not destination.exists():
                staging = destination.with_suffix(".pdf.part")
                staging.write_bytes(data)
                staging.replace(destination)
            pages = self.page_counter(destination)
            platform_pages = (attachment or {}).get("filePages")
            return PdfArtifactResult("SUCCESS", destination, digest, pages, int(platform_pages) if str(platform_pages or "").isdigit() else None)
        except (httpx.HTTPError, OSError, subprocess.SubprocessError, ValueError):
            return PdfArtifactResult("FAILED", error_code="PDF_DOWNLOAD_FAILED")

    @staticmethod
    def _fetch(url: str) -> bytes:
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.content

    @staticmethod
    def _pdfinfo_pages(path: Path) -> int:
        output = subprocess.run(["pdfinfo", str(path)], check=True, capture_output=True, text=True).stdout
        for line in output.splitlines():
            if line.startswith("Pages:"):
                return int(line.split(":", 1)[1].strip())
        raise ValueError("pdfinfo did not report a page count")
