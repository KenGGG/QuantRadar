"""Minimal synchronous client for the shared local MinerU API."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path, PurePosixPath

import httpx


def extract_mineru_zip(payload: bytes, destination: Path) -> Path:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        members = []
        for info in archive.infolist():
            name = PurePosixPath(info.filename.replace("\\", "/"))
            if name.is_absolute() or ".." in name.parts:
                raise ValueError("unsafe MinerU ZIP member")
            members.append((info, name))
        markdown = next((name for info, name in members if not info.is_dir() and name.suffix == ".md"), None)
        if markdown is None:
            raise ValueError("MinerU ZIP contains no Markdown")
        destination.mkdir(parents=True, exist_ok=False)
        for info, name in members:
            target = destination.joinpath(*name.parts)
            if info.is_dir(): target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(info))
    result = destination.joinpath(*markdown.parts)
    if not result.read_text(encoding="utf-8").strip(): raise ValueError("MinerU Markdown is empty")
    return result


class MineruClient:
    def __init__(self, api_url: str, timeout_seconds: int = 1800): self.api_url, self.timeout_seconds = api_url.rstrip("/"), timeout_seconds
    def health(self) -> dict:
        with httpx.Client(timeout=5) as client:
            response = client.get(f"{self.api_url}/health"); response.raise_for_status(); return response.json()

    def parse_pdf(self, pdf_path: Path) -> tuple[str, str]:
        with pdf_path.open("rb") as handle, httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(
                f"{self.api_url}/file_parse",
                files={"files": (pdf_path.name, handle, "application/pdf")},
                data={"backend": "pipeline", "return_md": "true", "response_format_zip": "false"},
            )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "completed":
            raise RuntimeError(f"MinerU parse did not complete: {payload.get('status')}")
        results = payload.get("results") or {}
        result = results.get(pdf_path.stem)
        if not isinstance(result, dict) or not isinstance(result.get("md_content"), str) or not result["md_content"].strip():
            raise ValueError("MinerU response contains no Markdown")
        return result["md_content"], str(payload.get("version") or "unknown")
