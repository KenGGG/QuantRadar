"""审计环境采集（Closing Phase 1：FULL_AUDIT_REPRO_PASS）。

为每次回测快照补充可复现审计字段：
    - dolt_commit      investment_data（Dolt）当前 HEAD commit
    - schema_hash      所用数据表结构的稳定哈希
    - strategy_hash    策略源码（或内置策略规范串）的哈希
    - config_hash      回测配置的稳定哈希
    - provider_version InvestmentDataProvider 版本
    - bullettrade_commit BulletTrade 基线 commit（vendor 无 .git，记录于 BASELINE.md）
    - quantradar_commit  QuantRadar 仓库当前 commit

以上字段与 daily_records 共同决定 result_hash；相同输入应产生一致 result_hash，
从而支撑「同配置可复现 + 审计」验证。
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from typing import Any, Dict, List, Optional

# InvestmentDataProvider 版本（与 docs 对齐；数据/接口变更时递增）
PROVIDER_VERSION = "1.0.0"

# BulletTrade 基线 commit（vendor/bullet-trade 为快照，无嵌套 .git；见 BASELINE.md）
BULLETTRADE_COMMIT = "be0451b"

# 参与 schema_hash 的核心数据表（Provider 真实依赖的表）
_SCHEMA_TABLES = [
    "final_a_stock_eod_price",
    "bao_a_stock_eod_info",
    "ts_a_stock_list",
    "ts_index_weight",
    "ts_trade_day_calendar",
    "final_a_stock_limit",
]


def _repo_root() -> str:
    # backend/quantradar/audit.py -> repo root（3 级上）
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def quantradar_commit() -> str:
    """QuantRadar 仓库当前 commit。

    优先直接读取 .git（避免沙箱/无关 git 配置导致的 subprocess 失败），
    失败再回退到 `git rev-parse HEAD`，最后回退环境变量或 'unknown'。
    """
    root = _repo_root()
    git_dir = os.path.join(root, ".git")
    try:
        head_path = os.path.join(git_dir, "HEAD")
        if os.path.isfile(head_path):
            with open(head_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content.startswith("ref:"):
                ref = content[4:].strip()
                ref_path = os.path.join(git_dir, *ref.split("/"))
                if os.path.isfile(ref_path):
                    with open(ref_path, "r", encoding="utf-8") as f:
                        return f.read().strip()
                # 可能在 packed-refs
                packed = os.path.join(git_dir, "packed-refs")
                if os.path.isfile(packed):
                    with open(packed, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("#") or not line:
                                continue
                            parts = line.split(" ")
                            if len(parts) == 2 and parts[1] == ref:
                                return parts[0]
            else:
                # detached HEAD：HEAD 直接是 commit
                return content
    except Exception:
        pass
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return os.environ.get("QUANTRADAR_COMMIT", "unknown")


def dolt_head_commit(connection: Any) -> Optional[str]:
    """investment_data（Dolt）当前 HEAD commit；不可用时返回 None。"""
    if connection is None:
        return None
    try:
        row = connection.query_one("SELECT commit_hash FROM dolt_log ORDER BY date DESC LIMIT 1")
        return row.get("commit_hash") if row else None
    except Exception:
        return None


def schema_hash(connection: Any) -> Optional[str]:
    """所用数据表（列名/类型）的稳定哈希（前 16 位）；不可用时返回 None。"""
    if connection is None:
        return None
    try:
        rows = connection.query(
            "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME IN (%s,%s,%s,%s,%s,%s) "
            "ORDER BY TABLE_NAME, ORDINAL_POSITION",
            tuple(_SCHEMA_TABLES),
        )
        payload = json.dumps(
            [[r["TABLE_NAME"], r["COLUMN_NAME"], r["COLUMN_TYPE"]] for r in rows],
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    except Exception:
        return None


def latest_data_date(connection: Any) -> Optional[str]:
    """investment_data 当前最新交易日（final_a_stock_eod_price.MAX(tradedate)）；不可用时返回 None。

    反映「数据库最新的数据时间」——价格数据覆盖前沿（文档值 2026-08-04）。
    """
    if connection is None:
        return None
    try:
        return connection.query_scalar("SELECT MAX(tradedate) FROM final_a_stock_eod_price")
    except Exception:
        return None


def _active_connection() -> Any:
    """取当前 active InvestmentDataProvider 的只读连接（不可用时 None）。"""
    try:
        from bullet_trade.data import get_data_provider

        from quantradar.providers.investment_data.provider import InvestmentDataProvider

        prov = get_data_provider()
        if isinstance(prov, InvestmentDataProvider):
            return getattr(prov, "_connection", None)
    except Exception:
        return None
    return None


def collect_audit_env(connection: Optional[Any] = None) -> Dict[str, Any]:
    """采集审计环境字段。connection 缺省时尝试使用 active provider 的连接。"""
    conn = connection if connection is not None else _active_connection()
    return {
        "provider": "investment_data",
        "provider_version": PROVIDER_VERSION,
        "dolt_commit": dolt_head_commit(conn),
        "schema_hash": schema_hash(conn),
        "latest_data_date": latest_data_date(conn),
        "bullettrade_commit": BULLETTRADE_COMMIT,
        "quantradar_commit": quantradar_commit(),
    }


def config_hash(config: Dict[str, Any], ndigits: int = 6) -> str:
    return hashlib.sha256(
        json.dumps(_norm(config, ndigits), sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def strategy_hash(source: Optional[str], config: Dict[str, Any], ndigits: int = 6) -> str:
    """策略哈希：有源码则 hash 源码；否则用内置策略规范串（基于配置，保证确定性）。"""
    if source:
        basis = "user:" + source
    else:
        basis = "builtin:buy_and_hold:" + json.dumps(_norm(config, ndigits), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def _norm(value: Any, ndigits: int = 6) -> Any:
    import datetime

    import pandas as pd

    if isinstance(value, (pd.Timestamp, datetime.datetime, datetime.date)):
        return pd.Timestamp(value).strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, float):
        return round(float(value), ndigits) if value == value else None
    if isinstance(value, dict):
        return {str(k): _norm(v, ndigits) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_norm(v, ndigits) for v in value]
    return value


__all__ = [
    "PROVIDER_VERSION",
    "BULLETTRADE_COMMIT",
    "quantradar_commit",
    "dolt_head_commit",
    "schema_hash",
    "latest_data_date",
    "collect_audit_env",
    "config_hash",
    "strategy_hash",
]
