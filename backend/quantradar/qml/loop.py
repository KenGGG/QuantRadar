"""Qlib Alpha158 + LightGBM 最小闭环（Train/Valid/Test/Prediction/IC/RankIC/TopK/Target Weight）。

防未来函数（关键）：
    - 标签：Alpha158 标准标签 Ref($close,-2)/Ref($close,-1)-1（未来 1 日收益），由 Qlib handler
      按点对齐生成；特征仅用历史（Ref($x, d>=0) / 滚动窗口），天然无前视。
    - 数据：来自 qlib_data（由 investment_data 真实导出），无未来数据注入。
    - 训练/验证/测试按时间切分，严格不重叠。

环境注意：
    - LGBModel.fit 走 qlib.workflow → mlflow；默认文件存储会污染仓库（./mlruns）且被禁用，
      故此处把 MLFLOW_TRACKING_URI 指向临时 sqlite 库，并允许文件存储兜底。
"""

from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

# 避免 qlib.workflow 的 mlflow 文件存储在仓库根目录生成 ./mlruns 污染 git。
# 关键：qlib 的默认 exp_manager.uri = file:<cwd>/mlruns，会忽略 MLFLOW_TRACKING_URI 环境变量，
# 因此必须在 qlib.init 时显式传入 exp_manager（指向临时目录下的 file store：track 与 artifact 都
# 落在 /tmp，绝不在仓库根生成 ./mlruns）。这里预置环境变量仅为兜底。
os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
_MLFLOW_TMP = tempfile.mkdtemp(prefix="qr_mlflow_")
MLFLOW_URI = f"file://{_MLFLOW_TMP}/mlruns"
os.environ["MLFLOW_TRACKING_URI"] = MLFLOW_URI


def _lazy_qlib():
    import qlib
    from qlib.contrib.data.handler import Alpha158
    from qlib.data.dataset import DatasetH
    from qlib.contrib.model.gbdt import LGBModel
    from qlib.contrib.eva.alpha import calc_ic

    return qlib, Alpha158, DatasetH, LGBModel, calc_ic


def _default_segments(start: str, end: str) -> Dict[str, Tuple[str, str]]:
    """按时间 6:2:2 切分 train/valid/test（不重叠，测试在最末，防泄漏）。"""
    from datetime import datetime, timedelta

    s = datetime.fromisoformat(start)
    e = datetime.fromisoformat(end)
    span = (e - s).days
    # 用标准库 datetime/timedelta，避免 pandas/numpy generic-timedelta 的 DeprecationWarning
    train_end = s + timedelta(days=int(span * 0.6))
    valid_end = s + timedelta(days=int(span * 0.8))
    return {
        "train": (s.strftime("%Y-%m-%d"), train_end.strftime("%Y-%m-%d")),
        "valid": (train_end.strftime("%Y-%m-%d"), valid_end.strftime("%Y-%m-%d")),
        "test": (valid_end.strftime("%Y-%m-%d"), e.strftime("%Y-%m-%d")),
    }


def topk_target_weights(
    pred: pd.Series,
    topk: int = 50,
) -> pd.DataFrame:
    """由测试期预测得分生成 Target Weight（等权 Top-K）。

    pred: 多级索引 (datetime, instrument) 的 Series。
    返回：DataFrame，index=交易日(datetime)，columns=证券(JQ代码)，values=权重（Top-K 内等权=1/K，其余 0）。
    每一行权重之和为 1（Top-K 非空时）。
    """
    if pred.empty:
        return pd.DataFrame()
    pdf = pred.reset_index()
    date_col = pdf.columns[0]
    inst_col = pdf.columns[1]
    score_col = pdf.columns[2]
    pdf[date_col] = pd.to_datetime(pdf[date_col])

    rows = {}
    for dt, grp in pdf.groupby(date_col):
        grp = grp.sort_values(score_col, ascending=False)
        grp = grp[grp[score_col].notna()]
        if len(grp) == 0:
            continue
        top = grp.head(min(topk, len(grp)))
        w = 1.0 / len(top)
        rows[dt] = {sec: w for sec in top[inst_col].tolist()}
    if not rows:
        return pd.DataFrame()
    wdf = pd.DataFrame(rows).T  # index=date, columns=instruments
    wdf = wdf.sort_index()
    return wdf


def run_qlib_loop(
    qlib_data_dir: str,
    start: str,
    end: str,
    topk: int = 50,
    num_boost_round: int = 200,
    early_stopping_rounds: int = 20,
    segments: Optional[Dict[str, Tuple[str, str]]] = None,
    market: str = "all",
) -> Dict[str, Any]:
    """运行 Alpha158 + LGBModel，返回指标与 Target Weight。

    Returns:
        {
          "segments", "train_samples", "ic_mean", "rankic_mean",
          "test_start", "test_end", "topk", "weights": DataFrame,
          "pred": Series, "feature_dim"
        }
    """
    qlib, Alpha158, DatasetH, LGBModel, calc_ic = _lazy_qlib()
    # 关键：显式覆盖默认 exp_manager.uri（否则 qlib 会用 file:<cwd>/mlruns 污染仓库根目录）。
    # 指向临时 file store（MLFLOW_ALLOW_FILE_STORE=true 已兜底允许），track + artifact 都在 /tmp。
    exp_manager = {
        "class": "MLflowExpManager",
        "module_path": "qlib.workflow.expm",
        "kwargs": {
            "uri": MLFLOW_URI,
            "default_exp_name": "qr_qml",
        },
    }
    qlib.init(
        provider_uri={"day": qlib_data_dir},
        region="cn",
        exp_manager=exp_manager,
    )

    if segments is None:
        segments = _default_segments(start, end)

    handler = Alpha158(
        instruments=market,
        start_time=start,
        end_time=end,
        infer_processors=[],
        learn_processors=[
            {"class": "DropnaLabel"},
            {"class": "CSZScoreNorm", "kwargs": {"fields_group": "label"}},
        ],
    )
    dataset = DatasetH(handler=handler, segments=segments)
    feature = dataset.prepare("train", col_set="feature")
    train_samples = int(feature.shape[0])
    feature_dim = int(feature.shape[1])

    model = LGBModel(
        loss="mse",
        num_boost_round=num_boost_round,
        early_stopping_rounds=early_stopping_rounds,
    )
    model.fit(dataset)

    pred = model.predict(dataset, segment="test")
    label = dataset.prepare("test", col_set="label")
    pred_1d = pred.squeeze() if hasattr(pred, "squeeze") else pred
    label_1d = label.squeeze() if hasattr(label, "squeeze") else label
    if getattr(label_1d, "ndim", 1) == 2:
        label_1d = label_1d.iloc[:, 0]
    ic, ric = calc_ic(pred_1d, label_1d)
    ic_mean = float(np.nanmean(ic)) if len(ic) else float("nan")
    rankic_mean = float(np.nanmean(ric)) if len(ric) else float("nan")

    weights = topk_target_weights(pred_1d, topk=topk)
    test_start, test_end = segments["test"]

    return {
        "segments": segments,
        "train_samples": train_samples,
        "feature_dim": feature_dim,
        "ic_mean": ic_mean,
        "rankic_mean": rankic_mean,
        "test_start": test_start,
        "test_end": test_end,
        "topk": topk,
        "weights": weights,
        "pred": pred_1d,
    }
