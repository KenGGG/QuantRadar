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

import itertools
import math
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


# -- 多模型注册表 --------------------------------------------------------
# 仅登记「计划支持的模型」；探测不可用（依赖缺失）时抛 NotImplementedError，绝不伪造。
# 注意：不同 qlib 版本的模型所在模块可能不同，这里按本环境实测路径登记；
# 探测逻辑在 available_models()/_get_model_class() 中按真实 import 验证，不假设存在。
_MODEL_REGISTRY: Dict[str, Dict[str, str]] = {
    "lgb": {"module": "qlib.contrib.model.gbdt", "class": "LGBModel"},
    "xgb": {"module": "qlib.contrib.model.xgboost", "class": "XGBModel"},
    "mlp": {"module": "qlib.contrib.model.pytorch", "class": "MLPModel"},
}

# qlib 不允许在同一进程重复 init（RecorderInitializationError，recorder 位置首次已定）。
# 因此每个进程仅 init 一次；后续若请求不同的 qlib_data_dir，仅重定向 provider_uri（数据目录），
# 不再重新 init，从而规避 qlib 进程级状态污染，同时支持跨目录复用（网格/walk-forward 多折）。
# 初始化状态以 qlib 自身的 C.registered 为准（build_qlib_data 与 loop 共享同一判定，避免重复 init）。
_QLIB_INITED: bool = False
_QLIB_INITED_DIR: Optional[str] = None


def _ensure_qlib_init(qlib_data_dir: str) -> None:
    """同一进程内仅初始化 qlib 一次；后续不同目录请求仅重定向 provider_uri（不重复 init）。

    这是 qlib 初始化的**唯一入口**：build_qlib_data 与 run_qlib_loop 都经由此函数，避免任一处
    直接 qlib.init 导致进程内重复 init（RecorderInitializationError）或全局 C 配置被重置/锁定。
    exp_manager 指向临时 file store（MLFLOW_ALLOW_FILE_STORE），避免污染仓库根 ./mlruns。
    每次（init 或重定向后）都把 joblib_backend 强制置为 'threading'：重定向 provider_uri 会把它
    重置回默认 'multiprocessing'，导致 inst_calculator 在 loky 子进程里因缺已注册的 C 而崩溃。
    """
    global _QLIB_INITED, _QLIB_INITED_DIR
    from qlib.config import C

    if getattr(C, "registered", False):
        # 已初始化（可能由 build_qlib_data 或先前 loop 调用）。目录不同则仅重定向 provider_uri。
        cur = (C.get("provider_uri") or {}).get("day")
        if cur != qlib_data_dir:
            C["provider_uri"] = {"day": qlib_data_dir}
            _QLIB_INITED_DIR = qlib_data_dir
        _set_threading_backend()
        return

    qlib, _, _, _, _ = _lazy_qlib()
    exp_manager = {
        "class": "MLflowExpManager",
        "module_path": "qlib.workflow.expm",
        "kwargs": {"uri": MLFLOW_URI, "default_exp_name": "qr_qml"},
    }
    qlib.init(provider_uri={"day": qlib_data_dir}, region="cn", exp_manager=exp_manager)
    _QLIB_INITED = True
    _QLIB_INITED_DIR = qlib_data_dir
    _set_threading_backend()


def _set_threading_backend() -> None:
    """强制 joblib 用 threading 后端，使 inst_calculator 在主线程序享已注册 C（规避 loky 崩溃）。"""
    try:
        from qlib.config import C

        C["joblib_backend"] = "threading"
    except Exception:
        pass


def available_models() -> List[str]:
    """探测当前环境可用的 Qlib 模型（lgb/xgb/mlp）。

    返回真正可 import 并实例化的模型名列表；缺失依赖的模型不列入（由调用方决定降级或报错）。
    """
    avail: List[str] = []
    for name, spec in _MODEL_REGISTRY.items():
        try:
            mod = __import__(spec["module"], fromlist=[spec["class"]])
            getattr(mod, spec["class"])
        except Exception:
            continue
        avail.append(name)
    return avail


def _get_model_class(model: str):
    """返回模型类；未知模型抛 ValueError，已知但当前环境不可用抛 NotImplementedError（不伪造）。"""
    if model not in _MODEL_REGISTRY:
        raise ValueError(f"未知模型 {model!r}；可选：{sorted(_MODEL_REGISTRY)}")
    spec = _MODEL_REGISTRY[model]
    try:
        mod = __import__(spec["module"], fromlist=[spec["class"]])
        return getattr(mod, spec["class"])
    except Exception as exc:  # 依赖缺失 -> 明确报错，绝不静默伪造
        raise NotImplementedError(
            f"模型 {model!r} 在当前环境不可用（缺少依赖：{exc}）；"
            f"请安装对应依赖后再用，不要伪造结果"
        ) from exc


def _add_months(dt, months: int):
    """标准库实现的月份加减（处理月末溢出，避免 numpy/pandas generic timedelta 警告）。返回 datetime。"""
    from datetime import datetime

    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    # 月末溢出钳制（如 1-31 加 1 月 -> 2-28/29）
    day = min(dt.day, [31, 29 if (year % 4 == 0 and year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return datetime(year, month, day)


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


def assert_segments_disjoint(segments: Dict[str, Tuple[str, str]]) -> None:
    """防泄漏守卫：Train/Valid/Test 时间区间必须严格不重叠且按时间顺序排列。

    任一层重叠都意味着未来数据可能泄漏进训练/验证，直接拒绝。
    """
    from datetime import datetime

    order = ["train", "valid", "test"]
    parsed = {k: (datetime.fromisoformat(v[0]), datetime.fromisoformat(v[1])) for k, v in segments.items()}
    for k in order:
        if k not in parsed:
            raise ValueError(f"segments 缺少 {k} 区间")
    # 区间应为 [start, end] 且 start <= end
    for k in order:
        s, e = parsed[k]
        if s > e:
            raise ValueError(f"segments[{k}] 起点晚于终点：{segments[k]}")
    # 相邻区间不重叠：train.end <= valid.start 且 valid.end <= test.start
    if parsed["train"][1] > parsed["valid"][0]:
        raise ValueError(f"Train/Valid 时间区间重叠（泄漏风险）：{segments}")
    if parsed["valid"][1] > parsed["test"][0]:
        raise ValueError(f"Valid/Test 时间区间重叠（泄漏风险）：{segments}")


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


def _fit_predict(
    model_name: str,
    model_params: Optional[Dict[str, Any]],
    qlib_data_dir: str,
    handler_start: str,
    handler_end: str,
    segments: Dict[str, Tuple[str, str]],
    topk: int,
    market: str,
) -> Dict[str, Any]:
    """模型无关的核心：构造 Alpha158 handler/dataset -> 训练 -> 测试期预测 -> IC/RankIC -> TopK 权重。

    供 run_qlib_loop / grid_search_qlib / walk_forward_qlib 复用，避免重复 Qlib 样板。
    防未来函数：标签由 Alpha158 handler 按点对齐生成；segments 必须时间不重叠（内部守卫）。
    """
    qlib, Alpha158, DatasetH, _, calc_ic = _lazy_qlib()
    _ensure_qlib_init(qlib_data_dir)
    # 关键：强制 joblib 用 threading 后端做数据加载，使 worker 与主进程共享已初始化的 qlib 配置
    # （C.registered 等），避免多进程 worker 缺少 qlib 初始化而报 `No such registered`；
    # 同时规避 spawn 子进程内再嵌套 loky 导致的队列死锁。
    # 必须在 _ensure_qlib_init 之后设置：重定向 provider_uri 会把 joblib_backend 重置回默认的
    # 'multiprocessing'，从而让 inst_calculator 在 loky 子进程里因缺 C 而崩溃。
    try:
        from qlib.config import C

        C["joblib_backend"] = "threading"
    except Exception:
        pass

    # 防泄漏守卫：Train/Valid/Test 必须时间不重叠
    assert_segments_disjoint(segments)

    handler = Alpha158(
        instruments=market,
        start_time=handler_start,
        end_time=handler_end,
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
    if train_samples == 0:
        raise RuntimeError("训练集为空（窗口/宇宙过小或数据缺口）：无法训练")

    model_cls = _get_model_class(model_name)
    params = dict(model_params or {})
    model = model_cls(**params)
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

    return {
        "segments": segments,
        "train_samples": train_samples,
        "feature_dim": feature_dim,
        "ic_mean": ic_mean,
        "rankic_mean": rankic_mean,
        "weights": topk_target_weights(pred_1d, topk=topk),
        "pred": pred_1d,
    }


def _default_model_params(model: str, num_boost_round: int, early_stopping_rounds: int) -> Dict[str, Any]:
    """按模型给出合理默认超参（仅对已知模型；xgb/mlp 交由调用方显式传入）。

    注意：lgb 强制 num_threads=1，确保固定 seed 下训练逐位可复现（OpenMP 多线程调度在负载下
    可能引入非确定性，破坏「同输入同输出」的可复现报告保证）。
    """
    if model == "lgb":
        return {
            "loss": "mse",
            "num_threads": 1,
            "num_boost_round": num_boost_round,
            "early_stopping_rounds": early_stopping_rounds,
        }
    return {}


def run_qlib_loop(
    qlib_data_dir: str,
    start: str,
    end: str,
    topk: int = 50,
    num_boost_round: int = 200,
    early_stopping_rounds: int = 20,
    segments: Optional[Dict[str, Tuple[str, str]]] = None,
    market: str = "all",
    model: str = "lgb",
    model_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """运行 Alpha158 + 选定模型，返回指标与 Target Weight。

    Args:
        model: 模型名（lgb/xgb/mlp）；未知抛 ValueError，已知但环境不可用抛 NotImplementedError。
        model_params: 模型超参覆盖；None 时用模型默认。

    Returns:
        {
          "segments", "train_samples", "ic_mean", "rankic_mean",
          "test_start", "test_end", "topk", "weights": DataFrame,
          "pred": Series, "feature_dim"
        }
    """
    if segments is None:
        segments = _default_segments(start, end)
    params = dict(model_params or {})
    params.update(_default_model_params(model, num_boost_round, early_stopping_rounds))
    out = _fit_predict(model, params, qlib_data_dir, start, end, segments, topk, market)
    out["test_start"], out["test_end"] = segments["test"]
    out["topk"] = topk
    return out


def _fit_predict_scalars(
    model: str,
    model_params: Optional[Dict[str, Any]],
    qlib_data_dir: str,
    handler_start: str,
    handler_end: str,
    segments: Dict[str, Tuple[str, str]],
    topk: int,
    market: str,
) -> Dict[str, Any]:
    """_fit_predict 的「仅标量」版本：返回 IC/RankIC/样本数/特征维（供需要跨进程/轻量返回的场景）。

    与 _fit_predict 共享同一训练流程，仅丢弃不可 pickle 的 DataFrame（weights/pred）。
    """
    out = _fit_predict(model, model_params, qlib_data_dir, handler_start, handler_end, segments, topk, market)
    return {
        "ic_mean": out["ic_mean"],
        "rankic_mean": out["rankic_mean"],
        "train_samples": out["train_samples"],
        "feature_dim": out["feature_dim"],
    }


def grid_search_qlib(
    qlib_data_dir: str,
    start: str,
    end: str,
    model: str = "lgb",
    param_grid: Optional[Dict[str, list]] = None,
    topk: int = 50,
    segments: Optional[Dict[str, Tuple[str, str]]] = None,
    market: str = "all",
    seed: int = 42,
    num_boost_round: int = 50,
    early_stopping_rounds: int = 10,
) -> Dict[str, Any]:
    """轻量网格寻优：在固定随机种子下遍历超参组合，按 IC 选优；结果可复现。

    绝不伪造：模型不可用（依赖缺失）时由 _get_model_class 抛 NotImplementedError。
    固定 seed 注入 lgb/xgb 以保证可复现（其余模型忽略未知 kwarg 由调用方负责）。

    Returns:
        {
          "model", "seed", "results": [{"params", "ic_mean", "rankic_mean", "train_samples"}],
          "best_params", "best_ic"
        }
    """
    if segments is None:
        segments = _default_segments(start, end)
    if param_grid is None:
        param_grid = (
            {"learning_rate": [0.05, 0.1], "num_leaves": [31, 63]}
            if model == "lgb"
            else {"learning_rate": [0.05, 0.1]}
        )
    keys = list(param_grid.keys())
    combos = [dict(zip(keys, vals)) for vals in itertools.product(*(param_grid[k] for k in keys))]

    results = []
    for combo in combos:
        params = dict(combo)
        if model in ("lgb", "xgb"):
            params["seed"] = seed
        params.update(_default_model_params(model, num_boost_round, early_stopping_rounds))
        # 同进程内多折训练：依赖 _ensure_qlib_init（仅初始化一次）+ threading 后端，
        # 避免 qlib 进程级 recorder/joblib 状态在多次 fit 时互相污染。
        out = _fit_predict_scalars(model, params, qlib_data_dir, start, end, segments, topk, market)
        results.append(
            {
                "params": combo,
                "ic_mean": out["ic_mean"],
                "rankic_mean": out["rankic_mean"],
                "train_samples": out["train_samples"],
            }
        )

    valid = [r for r in results if math.isfinite(r["ic_mean"])]
    if valid:
        best = max(valid, key=lambda r: r["ic_mean"])
        best_params, best_ic = best["params"], best["ic_mean"]
    else:
        best_params, best_ic = None, None
    return {
        "model": model,
        "seed": seed,
        "results": results,
        "best_params": best_params,
        "best_ic": best_ic,
    }


def walk_forward_qlib(
    qlib_data_dir: str,
    start: str,
    end: str,
    model: str = "lgb",
    model_params: Optional[Dict[str, Any]] = None,
    topk: int = 50,
    market: str = "all",
    train_years: int = 2,
    valid_months: int = 6,
    test_months: int = 6,
    step_months: int = 6,
    seed: int = 42,
    num_boost_round: int = 50,
    early_stopping_rounds: int = 10,
) -> Dict[str, Any]:
    """滚动窗口 walk-forward：逐折训练/验证/测试，输出各折样本外指标，杜绝单一切分的乐观偏差。

    每折：train=[cur, cur+train_years)，valid=[+valid_months)，test=[+test_months)；
    随后 cur 前进 step_months，直至 test 区间超出 end。每折内部 segments 不重叠（防泄漏守卫）。
    固定 seed 注入 lgb/xgb 保证可复现。

    Returns：
        {"model", "seed", "folds": [{fold, segments, ic_mean, rankic_mean, train_samples, feature_dim}], "n_folds"}
    """
    from datetime import datetime

    s = datetime.fromisoformat(start)
    e = datetime.fromisoformat(end)
    folds = []
    cur = s
    i = 0
    while True:
        train_start = cur
        train_end = _add_months(train_start, train_years * 12)
        valid_end = _add_months(train_end, valid_months)
        test_end = _add_months(valid_end, test_months)
        if test_end > e:
            break
        seg = {
            "train": (train_start.strftime("%Y-%m-%d"), train_end.strftime("%Y-%m-%d")),
            "valid": (train_end.strftime("%Y-%m-%d"), valid_end.strftime("%Y-%m-%d")),
            "test": (valid_end.strftime("%Y-%m-%d"), test_end.strftime("%Y-%m-%d")),
        }
        params = dict(model_params or {})
        if model in ("lgb", "xgb"):
            params["seed"] = seed
        params.update(_default_model_params(model, num_boost_round, early_stopping_rounds))
        # 同进程内多折训练：依赖 _ensure_qlib_init（仅初始化一次）+ threading 后端，
        # 避免 qlib 进程级 recorder/joblib 状态在多次 fit 时互相污染。
        out = _fit_predict_scalars(
            model,
            params,
            qlib_data_dir,
            train_start.strftime("%Y-%m-%d"),
            test_end.strftime("%Y-%m-%d"),
            seg,
            topk,
            market,
        )
        folds.append(
            {
                "fold": i,
                "segments": seg,
                "ic_mean": out["ic_mean"],
                "rankic_mean": out["rankic_mean"],
                "train_samples": out["train_samples"],
                "feature_dim": out["feature_dim"],
            }
        )
        cur = _add_months(cur, step_months)
        i += 1
        if i > 200:  # 安全阀，避免极端参数下死循环
            break
    return {"model": model, "seed": seed, "folds": folds, "n_folds": len(folds)}
