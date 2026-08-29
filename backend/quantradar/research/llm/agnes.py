"""Minimal Agnes adapter; network transport is injected for deterministic tests."""

from __future__ import annotations

import json
from typing import Any, Protocol

import httpx

from .chunking import SourceChunk
from .schemas import validate_analysis


class AgnesClient(Protocol):
    def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]: ...


class AgnesHttpClient:
    """OpenAI-compatible Agnes transport with bounded connection/request timeouts."""

    def __init__(self, base_url: str, api_key: str, model: str, *, session: httpx.Client | None = None):
        self.base_url, self.api_key, self.model = base_url.rstrip("/"), api_key, model
        self.session = session or httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0))

    def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        response = self.session.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "messages": messages, "response_format": {"type": "json_object"}},
        )
        response.raise_for_status()
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

    def analyze_report(self, markdown: str, chunks: list[SourceChunk]) -> dict[str, Any]:
        result = self.client.complete([{"role": "user", "content": markdown}])
        validation = validate_analysis(result, chunks)
        if not validation.valid:
            raise ValueError(";".join(validation.errors))
        return result

    def analyze_chunk(self, chunk: SourceChunk) -> dict[str, Any]:
        return self.analyze_report(chunk.text, [chunk])

    def synthesize_report(self, chunks: list[SourceChunk]) -> dict[str, Any]:
        return self.analyze_report("\n\n".join(chunk.text for chunk in chunks), chunks)
