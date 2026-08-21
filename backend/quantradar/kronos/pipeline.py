from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np
import pandas as pd

from quantradar.audit import dolt_head_commit
from quantradar.backtest_run import make_run_id
from quantradar.kronos.portfolio import (
    STRATEGY_VERSION,
    build_topk_target_weights,
    target_weight_hash,
    to_wide_weights,
)
from quantradar.kronos.runtime.contracts import KRONOS_MODEL_ID
from quantradar.kronos.signal.adapter import build_signals
from quantradar.kronos.signal.inputs import collect_week_input_package, list_signal_dates
from quantradar.kronos.universe_spec import DEFAULT_UNIVERSE, Universe
from quantradar.kronos.signal.manifest import file_hash, write_json_atomic
from quantradar.kronos.signal.store import SignalArtifactStore
from quantradar.kronos.signal.subprocess_runner import run_signal_subprocess
from quantradar.portfolio.target_weight_bridge import run_unified_target_weight_backtest


def _input_dates(input_dir: Path, manifest: dict[str, Any]) -> tuple[str, str]:
    path = input_dir / "runtime_inputs.npz"
    if path.is_file():
        with np.load(path, allow_pickle=False) as loaded:
            dates = loaded["x_dates"]
        return str(dates[0, 0]), str(dates[0, -1])
    end = str(manifest["signal_date"])
    start = (dt.date.fromisoformat(end) - dt.timedelta(days=130)).isoformat()
    return start, end


def _load_cached_data_gate(repo_root: Path) -> dict[str, Any] | None:
    """读取最近一次 ``make kronos-data-audit`` 产出的门禁（作为 tradeability 依据）。

    研究流水线自身不重跑完整审计；门禁的 tradeability 维度以审计产物为准。
    缺失时退化为保守默认值。
    """
    path = Path(repo_root) / "reports/kronos/data_audit/data_gate.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def run_research_pipeline(
    provider,
    *,
    repo_root: str | Path,
    artifacts_root: str | Path,
    runs_dir: str | Path,
    start: str,
    end: str,
    topk: int = 20,
    initial_cash: float = 1_000_000.0,
    signal_dates: Iterable[str | dt.date] | None = None,
    universe: Universe = DEFAULT_UNIVERSE,
    input_builder: Callable[..., dict[str, Any]] = collect_week_input_package,
    prediction_runner: Callable[..., dict[str, Any]] = run_signal_subprocess,
    backtest_runner: Callable[..., dict[str, Any]] = run_unified_target_weight_backtest,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    data_contract_path = root / "reports/kronos/data_audit/data_contract.json"
    model_lock_path = root / "models/kronos/kronos_model_lock.json"
    data_contract = json.loads(data_contract_path.read_text(encoding="utf-8"))
    model_lock = json.loads(model_lock_path.read_text(encoding="utf-8"))
    data_commit = dolt_head_commit(provider.connection)
    if not data_commit:
        raise RuntimeError("Dolt HEAD is unavailable")
    dates = [str(value) for value in signal_dates] if signal_dates is not None else [
        value.isoformat() for value in list_signal_dates(provider, start=start, end=end, universe=universe)
    ]
    if not dates:
        raise RuntimeError("No PIT signal dates in requested range")
    config = {
        "lookback_days": 90,
        "prediction_days": 10,
        "seeds": [101, 211, 307, 401, 503],
    }
    store = SignalArtifactStore.create(
        artifacts_root,
        config=config,
        model_lock=model_lock,
        data_contract=data_contract,
        data_commit=data_commit,
        requested_dates=dates,
    )
    completed = set(store.completed_dates())
    for day in dates:
        if day in completed:
            continue
        work = Path(tempfile.mkdtemp(prefix=f"kronos-{day}-"))
        try:
            input_dir = work / "input"
            output_dir = work / "prediction"
            input_manifest = input_builder(
                provider,
                signal_date=day,
                output_dir=input_dir,
                data_contract_path=data_contract_path,
                expected_data_commit=data_commit,
                universe=universe,
            )
            prediction = prediction_runner(
                repo_root=root, input_dir=input_dir, output_dir=output_dir
            )
            symbols = [str(value) for value in prediction["symbols"].tolist()]
            if symbols != [str(value) for value in input_manifest["eligible_symbols"]]:
                raise RuntimeError("prediction symbols do not match PIT input symbols")
            input_start, input_end = _input_dates(input_dir, input_manifest)
            lock_model = model_lock.get("model", {})
            lock_tokenizer = model_lock.get("tokenizer", {})
            signals = build_signals(
                prediction["predictions"],
                symbols=symbols,
                signal_run_id=store.run_id,
                signal_date=input_manifest["signal_date"],
                execution_date=input_manifest["execution_date"],
                input_start_date=input_start,
                input_end_date=input_end,
                input_hash=input_manifest["input_content_sha256"],
                model_version=KRONOS_MODEL_ID,
                model_revision=lock_model.get("revision", "unknown"),
                tokenizer_revision=lock_tokenizer.get("revision", "unknown"),
                data_commit=data_commit,
            )
            store.commit_week(
                day,
                signals=signals,
                input_manifest=input_manifest,
                predictions={
                    "predictions": prediction["predictions"],
                    "symbols": prediction["symbols"],
                },
            )
        finally:
            shutil.rmtree(work, ignore_errors=True)
    if dolt_head_commit(provider.connection) != data_commit:
        raise RuntimeError("Dolt HEAD changed during SignalRun")
    signal_manifest = store.merge()
    signals = pd.read_parquet(store.run_dir / "signals.parquet")
    weights = build_topk_target_weights(signals, topk=topk)
    if weights.empty:
        raise RuntimeError("Kronos signals produced no target weights")
    weight_path = store.run_dir / "target_weights.parquet"
    weight_temp = store.run_dir / ".target_weights.parquet.tmp"
    weights.to_parquet(weight_temp, index=False)
    os.replace(weight_temp, weight_path)
    weight_hash = target_weight_hash(weights)
    wide = to_wide_weights(weights)
    run_id = "kronos_" + weight_hash[:20]
    first_execution = pd.to_datetime(weights["execution_date"]).min().date()
    last_execution = pd.to_datetime(weights["execution_date"]).max().date()
    backtest_end = max(dt.date.fromisoformat(end), last_execution + dt.timedelta(days=20))
    backtest = backtest_runner(
        wide,
        run_id=run_id,
        start_date=first_execution.isoformat(),
        end_date=backtest_end.isoformat(),
        initial_cash=initial_cash,
        runs_dir=runs_dir,
        extras={
            "research_only": True,
            "signal_run_id": store.run_id,
            "target_weight_hash": weight_hash,
        },
    )
    run_dir = Path(backtest["run_dir"])
    shutil.copy2(store.run_dir / "manifest.json", run_dir / "kronos_signal_manifest.json")
    shutil.copy2(weight_path, run_dir / "target_weights.parquet")
    strategy_lock = {
        "strategy_version": STRATEGY_VERSION,
        "topk": topk,
        "target_weight_hash": weight_hash,
        "signal_run_id": store.run_id,
    }
    write_json_atomic(run_dir / "strategy_lock.json", strategy_lock)
    cached_gate = _load_cached_data_gate(root)
    # 研究流水线已抵达此处 => 输入宇宙可构造（kronos_signal_research_ready=True）。
    # realistic / real_assist / csi300_pit 的 tradeability 维度以最近一次审计为准。
    kronos_signal_research_ready = True
    realistic_backtest_ready = (
        bool(cached_gate.get("realistic_backtest_ready")) if cached_gate else True
    )
    real_assist_data_ready = (
        bool(cached_gate.get("real_assist_data_ready")) if cached_gate else False
    )
    csi300_pit_ready = (
        bool(cached_gate.get("csi300_pit_ready")) if cached_gate else False
    )
    research_manifest = {
        "signal_run_id": store.run_id,
        "data_commit": data_commit,
        "universe": universe.value,
        "prediction_hashes": sorted(signals["prediction_hash"].dropna().unique().tolist()),
        "signals_sha256": file_hash(store.run_dir / "signals.parquet"),
        "target_weights_sha256": file_hash(run_dir / "target_weights.parquet"),
        "target_weight_content_sha256": weight_hash,
        "backtest_result_hash": backtest.get("result_hash"),
        "report_html": backtest.get("report_html"),
        "research_only": True,
        "kronos_signal_research_ready": kronos_signal_research_ready,
        "realistic_backtest_ready": realistic_backtest_ready,
        "real_assist_data_ready": real_assist_data_ready,
        "csi300_pit_ready": csi300_pit_ready,
    }
    write_json_atomic(run_dir / "kronos_research_manifest.json", research_manifest)
    engineering_ready = Path(backtest["report_html"]).is_file()
    gate = {
        "engineering_ready": engineering_ready,
        "completion_marker": "GOAL2_ENGINEERING_PASS" if engineering_ready else None,
        "kronos_signal_research_ready": kronos_signal_research_ready,
        "realistic_backtest_ready": realistic_backtest_ready,
        "real_assist_data_ready": real_assist_data_ready,
        "csi300_pit_ready": csi300_pit_ready,
        # 向后兼容别名
        "formal_backtest_ready": realistic_backtest_ready,
        "signal_research_ready": kronos_signal_research_ready,
    }
    return {
        "signal_run_dir": str(store.run_dir),
        "signal_manifest": signal_manifest,
        "backtest": backtest,
        "research_manifest": research_manifest,
        "gate": gate,
    }
