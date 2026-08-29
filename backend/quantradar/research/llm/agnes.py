"""Minimal Agnes adapter; network transport is injected for deterministic tests."""

from __future__ import annotations

from typing import Any, Protocol

from .chunking import SourceChunk
from .schemas import validate_analysis


class AgnesClient(Protocol):
    def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]: ...


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
