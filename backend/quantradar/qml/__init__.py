"""QuantRadar Qlib 最小闭环包。

链路：investment_data(Dolt) → qlib_data → Alpha158+LGBModel → Prediction/IC/RankIC →
TopK Target Weight → BulletTrade 账户回测。

对外入口：run_qml_pipeline（串联 dump → loop → bridge）。
"""

from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, Optional

from .dump import build_qlib_data
from .loop import run_qlib_loop, topk_target_weights
from .bridge import run_target_weight_backtest


def run_qml_pipeline(
    *,
    start: str = "2018-01-01",
    end: str = "2024-12-31",
    max_instruments: int = 300,
    topk: int = 50,
    num_boost_round: int = 200,
    early_stopping_rounds: int = 20,
    initial_cash: float = 1_000_000.0,
    qlib_data_dir: Optional[str] = None,
    segments: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """运行完整 Qlib 最小闭环，返回各阶段结果字典。

    Args:
        start/end: 训练+回测窗口。
        max_instruments: 宇宙上限。
        topk: Top-K 选股数（Target Weight）。
        num_boost_round/early_stopping_rounds: LGBModel 参数。
        initial_cash: BulletTrade 账户初始资金。
        qlib_data_dir: qlib_data 输出目录；None 时用临时目录。
        segments: 自定义 train/valid/test 切分；None 时按 6:2:2 时间切分。

    Returns:
        {
          "dump": 元信息, "loop": 指标+weights, "backtest": snapshot,
          "test_start", "test_end"
        }
    """
    if qlib_data_dir is None:
        qlib_data_dir = tempfile.mkdtemp(prefix="qr_qlib_data_")

    dump_meta = build_qlib_data(
        qlib_data_dir,
        start=start,
        end=end,
        max_instruments=max_instruments,
    )

    loop_result = run_qlib_loop(
        qlib_data_dir,
        start=start,
        end=end,
        topk=topk,
        num_boost_round=num_boost_round,
        early_stopping_rounds=early_stopping_rounds,
        segments=segments,
    )

    weights = loop_result["weights"]
    test_start = loop_result["test_start"]
    test_end = loop_result["test_end"]

    engine, snapshot = run_target_weight_backtest(
        weights,
        start_date=test_start,
        end_date=test_end,
        initial_cash=initial_cash,
    )

    return {
        "dump": dump_meta,
        "loop": {
            "ic_mean": loop_result["ic_mean"],
            "rankic_mean": loop_result["rankic_mean"],
            "train_samples": loop_result["train_samples"],
            "feature_dim": loop_result["feature_dim"],
            "topk": loop_result["topk"],
            "weights_rows": int(weights.shape[0]) if not weights.empty else 0,
            "weights_cols": int(weights.shape[1]) if not weights.empty else 0,
        },
        "backtest": snapshot,
        "test_start": test_start,
        "test_end": test_end,
    }


__all__ = [
    "build_qlib_data",
    "run_qlib_loop",
    "topk_target_weights",
    "run_target_weight_backtest",
    "run_qml_pipeline",
]
