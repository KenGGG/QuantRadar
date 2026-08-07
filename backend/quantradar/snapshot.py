"""回测快照与可复现性（Phase 6）。

把一次 BacktestEngine 运行「环境 + 结果指纹」固化，便于复盘与审计：
  - 环境：provider 名称、initial_cash、start/end、frequency、策略参数(extras)、随机种子。
  - 数据 as-of：本次运行实际覆盖的最新交易日（来自 daily_records，反映所用数据边界）。
  - 结果指纹：daily_records 四舍五入后确定性哈希，用于复现校验。

指纹仅作复现凭证，不参与价格计算；价格仍来自 InvestmentDataProvider 实时查询。
若 investment_data 数据更新（区间扩展 / 因子修正），再次运行指纹随之变化 -> 视为新快照。
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
from typing import Any, Dict, List, Optional

import pandas as pd


def _to_native(value: Any, ndigits: int = 6) -> Any:
    """递归把 numpy/pandas 标量转成可 JSON 序列化的 Python 原生值并四舍五入。"""
    if isinstance(value, (pd.Timestamp, datetime.datetime, datetime.date)):
        return pd.Timestamp(value).strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, (pd.Timedelta,)):
        return str(value)
    # numpy / python 数值
    if isinstance(value, (int,)) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, (float,)):
        return round(float(value), ndigits) if value == value else None  # NaN -> None
    if hasattr(value, "item"):  # numpy scalar
        try:
            v = value.item()
        except Exception:
            v = value
        return _to_native(v, ndigits)
    if isinstance(value, dict):
        return {str(k): _to_native(v, ndigits) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_native(v, ndigits) for v in value]
    return value


def daily_records_fingerprint(records: List[Dict[str, Any]], ndigits: int = 6) -> str:
    """daily_records 的确定性 sha256 指纹（逐日记录四舍五入后排序序列化）。"""
    norm = [_to_native(r, ndigits) for r in (records or [])]
    payload = json.dumps(norm, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _fmt_ts(value: Any) -> Optional[str]:
    if value is None:
        return None
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def build_snapshot(
    engine: Any,
    *,
    extras: Optional[Dict[str, Any]] = None,
    seed: Optional[int] = None,
    data_asof: Optional[str] = None,
) -> Dict[str, Any]:
    """从一次「已运行」的 BacktestEngine 构建快照 manifest。

    Args:
        engine: 已 run() 完成的 BacktestEngine 实例。
        extras: 策略参数（g.extras），可空。
        seed: 随机种子（若有），可空。
        data_asof: 数据 as-of；缺省从 daily_records 最大日期推断（所用数据边界）。

    Returns:
        manifest dict（可 JSON 序列化）。
    """
    records = getattr(engine, "daily_records", []) or []
    asof = data_asof
    if asof is None and records:
        try:
            asof = max(
                pd.Timestamp(r.get("date")).strftime("%Y-%m-%d")
                for r in records
                if r.get("date") is not None
            )
        except Exception:
            asof = None

    config = {
        "provider": "investment_data",
        "initial_cash": getattr(engine, "initial_cash", None),
        "start_date": _fmt_ts(getattr(engine, "start_date", None)),
        "end_date": _fmt_ts(getattr(engine, "end_date", None)),
        "frequency": getattr(engine, "frequency", None),
        "seed": seed,
    }
    return {
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "config": config,
        "extras": extras,
        "data_asof": asof,
        "records_count": len(records),
        "result_fingerprint": daily_records_fingerprint(records),
    }


def save_snapshot(snapshot: Dict[str, Any], path: str) -> str:
    """保存快照到 JSON 文件，返回路径。"""
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2, sort_keys=True)
    return path


def load_snapshot(path: str) -> Dict[str, Any]:
    """从 JSON 文件读取快照 manifest。"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
