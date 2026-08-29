"""Deterministic Markdown chunk planning without truncating the source tail."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256


@dataclass(frozen=True)
class SourceChunk:
    chunk_id: str
    text: str
    chunk_sha256: str = ""


def plan_chunks(markdown: str, max_chars: int) -> list[SourceChunk]:
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    if len(markdown) <= max_chars:
        return [SourceChunk("chunk-0001", markdown, sha256(markdown.encode()).hexdigest())]

    parts = markdown.splitlines(keepends=True)
    groups: list[str] = []
    current = ""
    for part in parts:
        if current and len(current) + len(part) > max_chars:
            groups.append(current)
            current = ""
        while len(part) > max_chars:
            if current:
                groups.append(current)
                current = ""
            groups.append(part[:max_chars])
            part = part[max_chars:]
        current += part
    if current:
        groups.append(current)
    return [SourceChunk(f"chunk-{index:04d}", text, sha256(text.encode()).hexdigest()) for index, text in enumerate(groups, 1)]
