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
import uuid
from typing import Any, Dict, List, Optional

import pandas as pd

from .audit import collect_audit_env, config_hash, strategy_hash


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


def _fingerprint_obj(obj: Any, ndigits: int = 6) -> str:
    """任意可序列化对象的确定性 sha256 指纹。"""
    payload = json.dumps(_to_native(obj, ndigits), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def trades_fingerprint(engine: Any, ndigits: int = 6) -> str:
    """成交记录指纹：仅取可复现字段（标的/方向/数量/价格/金额/时间）。"""
    trades = getattr(engine, "trades", []) or []
    simplified = []
    for t in trades:
        simplified.append(
            {
                "security": getattr(t, "security", None),
                "action": getattr(t, "action", None),
                "amount": getattr(t, "amount", None),
                "price": getattr(t, "price", None),
                "value": getattr(t, "value", None),
                "datetime": _fmt_ts(getattr(t, "datetime", None)),
            }
        )
    return _fingerprint_obj(simplified, ndigits)


def positions_fingerprint(engine: Any, ndigits: int = 6) -> str:
    """持仓指纹：标的 -> 数量/成本/现价。"""
    port = getattr(getattr(engine, "context", None), "portfolio", None)
    positions = getattr(port, "positions", {}) or {}
    simplified = {}
    for sec, p in positions.items():
        simplified[sec] = {
            "amount": getattr(p, "amount", None),
            "avg_cost": getattr(p, "avg_cost", None),
            "price": getattr(p, "price", None),
        }
    return _fingerprint_obj(simplified, ndigits)


def compute_metrics(records: List[Dict[str, Any]], ndigits: int = 6) -> Dict[str, Any]:
    """从 daily_records 计算确定性指标（收益/回撤/天数），用于 Metrics 一致性校验。"""
    nav = [r.get("total_value") for r in (records or []) if r.get("total_value") is not None]
    if not nav:
        return {}
    start = float(nav[0])
    end = float(nav[-1])
    total_return = (end - start) / start if start else 0.0
    peak = start
    max_drawdown = 0.0
    for v in nav:
        v = float(v)
        peak = max(peak, v)
        if peak:
            max_drawdown = min(max_drawdown, (v - peak) / peak)
    return {
        "final_total_value": round(end, ndigits),
        "total_return": round(total_return, ndigits),
        "max_drawdown": round(max_drawdown, ndigits),
        "days": len(nav),
    }


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
    audit_env: Optional[Dict[str, Any]] = None,
    strategy_source: Optional[str] = None,
    connection: Optional[Any] = None,
    security: Optional[str] = None,
    amount: Optional[int] = None,
    benchmark: Optional[str] = None,
    fq: Optional[str] = None,
) -> Dict[str, Any]:
    """从一次「已运行」的 BacktestEngine 构建快照 manifest（含完整审计字段）。

    Hash 语义（三者职责分明，见 docs）：
      - run_id        每次提交唯一 UUID（标识「这一次运行实例」，不可复现，仅用于检索）。
      - snapshot_hash 实验设置指纹 = f(config_hash, strategy_hash, data_asof, dolt_commit,
                       provider_version)，**确定性**：相同数据+策略+配置必得相同值，用于判定
                      两次运行是否为「同一实验设置」。
      - result_hash   输出指纹 = f(daily_records, trades, positions, metrics)，**确定性**：
                       相同设置+相同数据必得相同值，用于判定结果可复现。

    Args:
        engine: 已 run() 完成的 BacktestEngine 实例。
        extras: 策略参数（g.extras），可空。
        seed: 随机种子（若有），可空。
        data_asof: 数据 as-of；缺省从 daily_records 最大日期推断（所用数据边界）。
        audit_env: 审计环境字段（dolt_commit/schema_hash/...）；缺省自动采集。
        strategy_source: 策略源码（用户提交）；内置策略传 None 由配置推导规范串。
        connection: 只读连接（用于采集 dolt_commit/schema_hash）；缺省用 active provider。
        security/amount/benchmark: 回测标的/每笔数量/基准（引擎未持久化这些属性，由调用方显式传入）。

    Returns:
        manifest dict（可 JSON 序列化），含 snapshot_id / config / config_hash / strategy_hash /
        snapshot_hash / environment / result_hash / metrics，支撑可复现与审计验证。
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
        "security": security if security is not None else getattr(engine, "security", None),
        "initial_cash": getattr(engine, "initial_cash", None),
        "start_date": _fmt_ts(getattr(engine, "start_date", None)),
        "end_date": _fmt_ts(getattr(engine, "end_date", None)),
        "frequency": getattr(engine, "frequency", None),
        "amount": amount if amount is not None else getattr(engine, "amount", None),
        "benchmark": benchmark if benchmark is not None else getattr(engine, "benchmark", None),
        "fq": fq if fq is not None else getattr(engine, "fq", None),
        "seed": seed,
    }
    metrics = compute_metrics(records)
    env = audit_env if audit_env is not None else collect_audit_env(connection)
    c_hash = config_hash(config)
    s_hash = strategy_hash(strategy_source, config)
    # 实验设置指纹（确定性）：相同数据+策略+配置 => 相同值，用于判定「同一实验设置」。
    snapshot_hash = hashlib.sha256(
        "|".join(
            [
                c_hash,
                s_hash,
                str(asof),
                str(env.get("dolt_commit")),
                str(env.get("provider_version")),
            ]
        ).encode("utf-8")
    ).hexdigest()
    daily_fp = daily_records_fingerprint(records)
    result_hash = hashlib.sha256(
        "|".join(
            [
                daily_fp,
                trades_fingerprint(engine),
                positions_fingerprint(engine),
                _fingerprint_obj(metrics),
            ]
        ).encode("utf-8")
    ).hexdigest()
    return {
        "snapshot_id": uuid.uuid4().hex,
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "config": config,
        "config_hash": c_hash,
        "strategy_hash": s_hash,
        "snapshot_hash": snapshot_hash,
        "extras": extras,
        "data_asof": asof,
        "records_count": len(records),
        "result_fingerprint": daily_fp,
        "result_hash": result_hash,
        "metrics": metrics,
        "environment": env,
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
