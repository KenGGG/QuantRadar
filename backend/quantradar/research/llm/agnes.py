"""Minimal Agnes adapter; network transport is injected for deterministic tests."""

from __future__ import annotations

import json
import time
from typing import Any, Protocol

import httpx

from .chunking import SourceChunk
from .schemas import validate_analysis


class AgnesClient(Protocol):
    def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]: ...


class RetryableAgnesError(RuntimeError):
    pass


class TerminalAgnesError(RuntimeError):
    pass


class AgnesHttpClient:
    """OpenAI-compatible Agnes transport with bounded connection/request timeouts."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        timeout_seconds: int = 180,
        requests_per_minute: int = 19,
        session: httpx.Client | None = None,
        clock=time.monotonic,
        sleeper=time.sleep,
    ):
        if requests_per_minute < 1:
            raise ValueError("requests_per_minute must be positive")
        self.base_url, self.api_key, self.model = base_url.rstrip("/"), api_key, model
        self.session = session or httpx.Client(timeout=httpx.Timeout(timeout_seconds, connect=10.0))
        self._minimum_interval = 60.0 / requests_per_minute
        self._clock, self._sleeper, self._last_request_at = clock, sleeper, None

    def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        if self._last_request_at is not None:
            remaining = self._minimum_interval - (self._clock() - self._last_request_at)
            if remaining > 0:
                self._sleeper(remaining)
        self._last_request_at = self._clock()
        try:
            response = self.session.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "messages": messages, "response_format": {"type": "json_object"}},
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise RetryableAgnesError(type(exc).__name__) from exc
        if response.status_code == 429 or response.status_code >= 500:
            raise RetryableAgnesError(f"HTTP_{response.status_code}")
        if response.status_code >= 400:
            raise TerminalAgnesError(f"HTTP_{response.status_code}")
        content = response.json()["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("Agnes returned non-text completion content")
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("Agnes returned non-object JSON")
        return parsed


class AgnesAnalyzer:
    def __init__(self, client: AgnesClient):
        self.client = client

    def analyze_report(self, markdown: str, chunks: list[SourceChunk], *, report_id: int | None = None, markdown_sha256: str | None = None, task: str = "Analyze the supplied research-report Markdown.") -> dict[str, Any]:
        authoritative_hashes = {chunk.chunk_id: chunk.chunk_sha256 for chunk in chunks}
        evidence_contract = [
            {"chunk_id": chunk.chunk_id, "chunk_sha256": chunk.chunk_sha256}
            for chunk in chunks
        ]
        contract = (
            f"{task} Return one JSON object only. "
            "Required non-empty fields: research_type (MARKET or QUANT), one_line_summary, and evidence. "
            "Each evidence item must cite only one of these exact chunk identifiers and hashes: "
            f"{json.dumps(evidence_contract, ensure_ascii=False)}. "
            "Evidence items must include chunk_id and chunk_sha256. Do not invent source identifiers."
        )
        result = self.client.complete([
            {"role": "system", "content": contract},
            {"role": "user", "content": markdown},
        ])
        def scope_evidence(payload: dict[str, Any]) -> dict[str, Any]:
            for evidence in payload.get("evidence", []):
                if not isinstance(evidence, dict):
                    continue
                chunk_id = evidence.get("chunk_id")
                if chunk_id in authoritative_hashes:
                    evidence["chunk_sha256"] = authoritative_hashes[chunk_id]
                if report_id is not None:
                    evidence.setdefault("report_id", report_id)
                    evidence.setdefault("markdown_sha256", markdown_sha256)
            return payload

        result = scope_evidence(result)
        validation = validate_analysis(result, chunks, report_id=report_id, markdown_sha256=markdown_sha256)
        if not validation.valid:
            repair_contract = (
                f"{contract} The previous JSON failed validation with: {';'.join(validation.errors)}. "
                f"Previous JSON: {json.dumps(result, ensure_ascii=False)}. "
                "Return corrected JSON only; preserve claims only when their evidence cites the exact allowed chunk_id and chunk_sha256."
            )
            result = scope_evidence(self.client.complete([
                {"role": "system", "content": repair_contract},
                {"role": "user", "content": markdown},
            ]))
            validation = validate_analysis(result, chunks, report_id=report_id, markdown_sha256=markdown_sha256)
        if not validation.valid:
            raise ValueError(";".join(validation.errors))
        return result

    def analyze_chunk(self, chunk: SourceChunk, *, report_id: int | None = None, markdown_sha256: str | None = None) -> dict[str, Any]:
        return self.analyze_report(chunk.text, [chunk], report_id=report_id, markdown_sha256=markdown_sha256)

    def synthesize_report(self, chunks: list[SourceChunk], chunk_analyses: list[dict[str, Any]], *, report_id: int | None = None, markdown_sha256: str | None = None) -> dict[str, Any]:
        payload = json.dumps(
            {"chunk_analyses": [
                {"chunk_id": chunk.chunk_id, "chunk_sha256": chunk.chunk_sha256, "analysis": analysis}
                for chunk, analysis in zip(chunks, chunk_analyses, strict=True)
            ]},
            ensure_ascii=False,
        )
        return self.analyze_report(
            payload,
            chunks,
            report_id=report_id,
            markdown_sha256=markdown_sha256,
            task="Synthesize a report-level analysis from the supplied chunk_analyses.",
        )
