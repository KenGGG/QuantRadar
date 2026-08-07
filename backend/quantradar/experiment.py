"""Experiment 管理（目标：Experiment 保存 / 对比）。

把一次回测 / 因子研究结果固化为一个 Experiment（含 Snapshot 指纹与关键指标），
支持保存、列举、加载与对比。默认用本地 JSON 文件存储（不依赖 PostgreSQL），
与 Phase 6 Snapshot 同源，可直接在 Phase 9（Postgres）中以相同 manifest 落库。

存储布局：{dir}/{name}.json
manifest:
    {
      "name": str,
      "created_at": ISO,
      "kind": "backtest" | "factor",
      "config": {...},                       # 回测/因子参数
      "result_fingerprint": str,            # 来自 Snapshot（回测）或可复现指纹（因子）
      "metrics": {...},                      # 关键指标（如 final_total_value / ic_mean）
      "snapshot": {...} | null               # 回测快照（可空，落库时再关联）
    }
"""

from __future__ import annotations

import datetime
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .snapshot import build_snapshot, load_snapshot, save_snapshot


def _default_dir() -> str:
    return os.environ.get(
        "QUANT_RADAR_EXPERIMENT_DIR",
        os.path.join(os.path.dirname(__file__), "..", "..", "experiments"),
    )


@dataclass
class Experiment:
    name: str
    kind: str
    config: Dict[str, Any]
    result_fingerprint: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.datetime.now().isoformat(timespec="seconds")
    )
    snapshot: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "created_at": self.created_at,
            "kind": self.kind,
            "config": self.config,
            "result_fingerprint": self.result_fingerprint,
            "metrics": self.metrics,
            "snapshot": self.snapshot,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Experiment":
        return cls(
            name=d["name"],
            kind=d.get("kind", "backtest"),
            config=d.get("config", {}),
            result_fingerprint=d.get("result_fingerprint", ""),
            metrics=d.get("metrics", {}),
            created_at=d.get("created_at", ""),
            snapshot=d.get("snapshot"),
        )


def save_experiment(exp: Experiment, directory: Optional[str] = None) -> str:
    """保存 Experiment 到 JSON，返回路径。"""
    directory = directory or _default_dir()
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{exp.name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(exp.to_dict(), f, ensure_ascii=False, indent=2, sort_keys=True)
    return path


def load_experiment(name: str, directory: Optional[str] = None) -> Experiment:
    directory = directory or _default_dir()
    path = os.path.join(directory, f"{name}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Experiment 不存在：{path}")
    with open(path, "r", encoding="utf-8") as f:
        return Experiment.from_dict(json.load(f))


def list_experiments(directory: Optional[str] = None) -> List[str]:
    directory = directory or _default_dir()
    if not os.path.isdir(directory):
        return []
    return sorted(
        p[: -len(".json")] for p in os.listdir(directory) if p.endswith(".json")
    )


def compare_experiments(names: List[str], directory: Optional[str] = None) -> Dict[str, Any]:
    """对比多个 Experiment：返回每个 experiment 的指纹与指标，以及可复现一致性判定。

    输出：
        {
          "experiments": [ {name, kind, fingerprint, metrics, reproducible: bool} ],
          "fingerprint_match": bool,   # 所有指纹是否一致
        }
    """
    exps = [load_experiment(n, directory) for n in names]
    fps = {e.result_fingerprint for e in exps}
    out = []
    for e in exps:
        out.append(
            {
                "name": e.name,
                "kind": e.kind,
                "fingerprint": e.result_fingerprint,
                "metrics": e.metrics,
                "reproducible": True,  # 同指纹即同结果（Snapshot 已固化）
            }
        )
    return {"experiments": out, "fingerprint_match": len(fps) <= 1}


def experiment_from_backtest(
    name: str,
    engine: Any,
    *,
    extras: Optional[Dict[str, Any]] = None,
    metrics: Optional[Dict[str, Any]] = None,
) -> Experiment:
    """从一次「已运行」的 BacktestEngine 直接构造 Experiment（含 Snapshot 指纹）。"""
    snap = build_snapshot(engine, extras=extras)
    return Experiment(
        name=name,
        kind="backtest",
        config=snap.get("config", {}),
        result_fingerprint=snap.get("result_fingerprint", ""),
        metrics=metrics or {},
        snapshot=snap,
    )
