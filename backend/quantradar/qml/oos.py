"""样本外（OOS）稳健性验证：walk-forward 多折 + 可复现报告。

设计原则：
- 不伪造：完全依赖 walk_forward_qlib / grid_search_qlib（真实 Alpha158+LGBModel，
  标签按点对齐防未来函数，segments 严格不重叠）；任何失败都如实抛出，绝不编造指标。
- 可复现：固定随机种子 + 报告内记录完整 config 与运行环境（git commit / 版本），
  同输入必产出逐字节一致的 JSON 报告。
- 样本外稳健性：以 walk-forward 各折「测试期」IC 作为真实样本外表现，聚合均值/标准差/
  正 IC 折占比（hit ratio），避免单一切分的乐观偏差。
"""

from __future__ import annotations

import math
import subprocess
from typing import Any, Dict, List, Optional

import numpy as np

from .loop import grid_search_qlib, walk_forward_qlib


def _py(v: Any) -> Any:
    """标量 → JSON 友好类型（numpy float/int → python float/int）。"""
    if isinstance(v, (np.floating, float)):
        return float(v)
    if isinstance(v, (np.integer, int)):
        return int(v)
    return v


def _collect_environment() -> Dict[str, str]:
    """尽力采集运行环境（git commit / 关键包版本），失败项记为 unknown，绝不联网。"""
    env: Dict[str, str] = {}
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        env["git_commit"] = head.stdout.strip() or "unknown"
    except Exception:
        env["git_commit"] = "unknown"
    for mod in ("qlib", "lightgbm", "numpy", "pandas"):
        try:
            m = __import__(mod)
            env[f"{mod}_version"] = getattr(m, "__version__", "unknown")
        except Exception:
            env[f"{mod}_version"] = "unknown"
    import sys

    env["python_version"] = sys.version.split()[0]
    return env


def run_research_oos(
    qlib_data_dir: str,
    start: str,
    end: str,
    model: str = "lgb",
    topk: int = 50,
    train_years: int = 2,
    valid_months: int = 6,
    test_months: int = 6,
    step_months: int = 6,
    seed: int = 42,
    num_boost_round: int = 50,
    early_stopping_rounds: int = 10,
    do_grid: bool = True,
    param_grid: Optional[Dict[str, list]] = None,
    market: str = "all",
) -> Dict[str, Any]:
    """端到端样本外稳健性验证，返回结构化（JSON 可序列化）报告。

    Args:
        qlib_data_dir: 已构建的 qlib_data 目录（由 build_qlib_data 产出）。
        start/end: 总体窗口（网格与 walk-forward 都在此区间内）。
        model: 模型名（默认 lgb；xgb/mlp 缺依赖由 _get_model_class 抛 NotImplementedError）。
        do_grid: 是否先做 in-sample 网格寻优（按 IC 选优超参），结果一并记入报告。
        seed: 固定随机种子，保证可复现。

    Returns:
        {
          "config": {...}, "grid": {...} | None, "folds": [...],
          "oos": {n_folds, mean_ic, std_ic, mean_rankic, folds_with_positive_ic, positive_ic_ratio},
          "environment": {...}
        }
    """
    config: Dict[str, Any] = {
        "model": model,
        "topk": topk,
        "train_years": train_years,
        "valid_months": valid_months,
        "test_months": test_months,
        "step_months": step_months,
        "seed": seed,
        "num_boost_round": num_boost_round,
        "early_stopping_rounds": early_stopping_rounds,
        "market": market,
        "start": start,
        "end": end,
        "qlib_data_dir": qlib_data_dir,
    }

    grid_out: Optional[Dict[str, Any]] = None
    if do_grid:
        g = grid_search_qlib(
            qlib_data_dir, start, end, model=model, param_grid=param_grid,
            topk=topk, seed=seed, num_boost_round=num_boost_round,
            early_stopping_rounds=early_stopping_rounds,
        )
        grid_out = {
            "model": g["model"],
            "seed": g["seed"],
            "best_params": g["best_params"],
            "best_ic": _py(g["best_ic"]),
            "n_combos": len(g["results"]),
            "results": [
                {
                    "params": r["params"],
                    "ic_mean": _py(r["ic_mean"]),
                    "rankic_mean": _py(r["rankic_mean"]),
                    "train_samples": r["train_samples"],
                }
                for r in g["results"]
            ],
        }

    wf = walk_forward_qlib(
        qlib_data_dir, start, end, model=model, topk=topk,
        train_years=train_years, valid_months=valid_months,
        test_months=test_months, step_months=step_months, seed=seed,
        num_boost_round=num_boost_round, early_stopping_rounds=early_stopping_rounds,
    )

    folds: List[Dict[str, Any]] = [
        {
            "fold": f["fold"],
            "segments": {k: list(v) for k, v in f["segments"].items()},
            "ic_mean": _py(f["ic_mean"]),
            "rankic_mean": _py(f["rankic_mean"]),
            "train_samples": f["train_samples"],
            "feature_dim": f["feature_dim"],
        }
        for f in wf["folds"]
    ]

    ics = [f["ic_mean"] for f in folds if math.isfinite(f["ic_mean"])]
    rankics = [f["rankic_mean"] for f in folds if math.isfinite(f["rankic_mean"])]
    n = len(ics)
    mean_ic = float(sum(ics) / n) if n else float("nan")
    std_ic = float(np.std(ics)) if n else float("nan")
    mean_rankic = float(sum(rankics) / len(rankics)) if rankics else float("nan")
    pos = sum(1 for x in ics if x > 0)

    oos: Dict[str, Any] = {
        "n_folds": len(folds),
        "mean_ic": mean_ic,
        "std_ic": std_ic,
        "mean_rankic": mean_rankic,
        "folds_with_positive_ic": pos,
        "positive_ic_ratio": (pos / n) if n else float("nan"),
    }

    return {
        "config": config,
        "grid": grid_out,
        "folds": folds,
        "oos": oos,
        "environment": _collect_environment(),
    }


def render_oos_markdown(report: Dict[str, Any]) -> str:
    """把结构化报告渲染为可读 Markdown（供 scripts/research_oos.py 落盘）。"""
    c = report["config"]
    o = report["oos"]
    lines: List[str] = []
    lines.append("# QuantRadar 样本外（OOS）稳健性验证报告")
    lines.append("")
    lines.append("## 配置")
    for k in ("model", "topk", "train_years", "valid_months", "test_months",
              "step_months", "seed", "num_boost_round", "early_stopping_rounds",
              "start", "end"):
        lines.append(f"- **{k}**: {c[k]}")
    lines.append(f"- **qlib_data_dir**: {c['qlib_data_dir']}")
    lines.append("")
    lines.append("## 样本外聚合指标")
    lines.append(f"- 折数（OOS 窗口）: {o['n_folds']}")
    lines.append(f"- 平均样本外 IC: {o['mean_ic']:.4f}" if math.isfinite(o['mean_ic']) else "- 平均样本外 IC: NaN")
    lines.append(f"- 样本外 IC 标准差: {o['std_ic']:.4f}" if math.isfinite(o['std_ic']) else "- 样本外 IC 标准差: NaN")
    lines.append(f"- 平均样本外 RankIC: {o['mean_rankic']:.4f}" if math.isfinite(o['mean_rankic']) else "- 平均样本外 RankIC: NaN")
    lines.append(f"- 正 IC 折数: {o['folds_with_positive_ic']} / {o['n_folds']}")
    lines.append(f"- 正 IC 折占比 (hit ratio): {o['positive_ic_ratio']:.2%}" if math.isfinite(o['positive_ic_ratio']) else "- 正 IC 折占比: NaN")
    lines.append("")
    if report.get("grid"):
        g = report["grid"]
        lines.append("## In-sample 网格寻优（按 IC 选优）")
        lines.append(f"- 组合数: {g['n_combos']}")
        lines.append(f"- 最优超参: {g['best_params']}")
        lines.append(f"- 最优 IC: {g['best_ic']}" if g['best_ic'] is not None else "- 最优 IC: 无有限结果")
        lines.append("")
    lines.append("## 各折样本外明细")
    lines.append("| fold | train | valid | test | IC | RankIC | train_samples |")
    lines.append("|---|---|---|---|---|---|---|")
    for f in report["folds"]:
        seg = f["segments"]
        ic = f"{f['ic_mean']:.4f}" if math.isfinite(f["ic_mean"]) else "NaN"
        ric = f"{f['rankic_mean']:.4f}" if math.isfinite(f["rankic_mean"]) else "NaN"
        lines.append(
            f"| {f['fold']} | {seg['train'][0]}~{seg['train'][1]} | "
            f"{seg['valid'][0]}~{seg['valid'][1]} | {seg['test'][0]}~{seg['test'][1]} | "
            f"{ic} | {ric} | {f['train_samples']} |"
        )
    lines.append("")
    lines.append("## 运行环境")
    for k, v in report["environment"].items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    return "\n".join(lines)
