from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParseQuality:
    char_count: int
    replacement_char_ratio: float
    table_count: int
    image_count: int
    status: str


def assess_markdown(text: str) -> ParseQuality:
    char_count = len(text.strip())
    replacement_ratio = text.count("�") / max(len(text), 1)
    table_count = sum(1 for line in text.splitlines() if line.strip().startswith("|") and "-" in line)
    image_count = text.count("![](")
    normalized = text.replace(" ", "").replace("\n", "")
    navigation_only = any(marker in normalized.lower() for marker in ("登录后查看全文", "请登录", "accessdenied", "authenticationrequired"))
    status = "PARSE_FAILED" if navigation_only else "PARSE_OK" if char_count >= 20 and replacement_ratio <= 0.02 else "PARSE_PARTIAL" if char_count else "PARSE_FAILED"
    return ParseQuality(char_count, replacement_ratio, table_count, image_count, status)
