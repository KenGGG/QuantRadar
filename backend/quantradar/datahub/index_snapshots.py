"""Normalization for the explicitly versioned DataHub V3 index snapshots."""
from __future__ import annotations

from typing import Any


def _symbol(code: Any, exchange: Any = None) -> str:
    text = str(code).strip().split('.')[0].zfill(6)
    if not text.isdigit() or len(text) != 6:
        raise ValueError(f"invalid constituent code: {code!r}")
    exchange_text = str(exchange or "")
    if "上海" in exchange_text or exchange_text.upper() in {"SH", "SSE"} or text.startswith(('6', '9')):
        return text + '.SH'
    return text + '.SZ'


def normalize_csi_constituents(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"security_code": _symbol(row.get("成分券代码"), row.get("交易所")),
             "security_name": row.get("成分券名称"), "exchange": row.get("交易所")}
            for row in rows]


def normalize_csi_weights(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        raw = float(row["权重"])
        result.append({"security_code": _symbol(row.get("成分券代码"), row.get("交易所")),
                       "weight_raw": raw, "weight_unit": "PERCENT", "weight_fraction": raw / 100.0})
    return result


def normalize_sw_components(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"security_code": _symbol(row.get("证券代码")), "security_name": row.get("证券名称"),
             "weight_raw": None if row.get("最新权重") is None else float(row["最新权重"]),
             "member_effective_date": None if row.get("计入日期") is None else str(row["计入日期"])[:10],
             "member_effective_semantics": "SOURCE_MEMBER_INCLUSION_DATE",
             "member_effective_evidence": "akshare:index_component_sw:计入日期"}
            for row in rows]


def validate_index_snapshot_candidate(version: dict[str, Any], members: list[dict[str, Any]]) -> dict[str, Any]:
    required = ("dataset_type", "index_code", "observed_at", "raw_sha256", "content_hash", "source",
                "adapter_version", "effective_semantics", "qualification", "pit_status")
    errors = ["missing " + field for field in required if not version.get(field)]
    if len(str(version.get("raw_sha256") or "")) != 64:
        errors.append("invalid raw_sha256")
    if len(str(version.get("content_hash") or "")) != 64:
        errors.append("invalid content_hash")
    if not members:
        errors.append("empty member snapshot")
    codes = [row.get("security_code") for row in members]
    if len(codes) != len(set(codes)) or any(not code or len(str(code)) != 9 for code in codes):
        errors.append("invalid or duplicate security_code")
    return {"status": "PASS" if not errors else "FAIL", "members": len(members), "errors": errors}
