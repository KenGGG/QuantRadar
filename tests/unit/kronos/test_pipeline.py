from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from quantradar.kronos.pipeline import run_research_pipeline


class _Connection:
    def query_one(self, sql, params=None):
        return {"commit_hash": "dolt-rev"}


class _Provider:
    connection = _Connection()


def test_pipeline_links_prediction_signal_weight_and_native_report(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "models/kronos").mkdir(parents=True)
    (repo / "models/kronos/kronos_model_lock.json").write_text(
        json.dumps(
            {
                "model": {"revision": "model-rev"},
                "tokenizer": {"revision": "tok-rev"},
            }
        )
    )
    (repo / "reports/kronos/data_audit").mkdir(parents=True)
    (repo / "reports/kronos/data_audit/data_contract.json").write_text(
        json.dumps({"price": "qfq"})
    )

    def input_builder(provider, *, signal_date, output_dir, **kwargs):
        Path(output_dir).mkdir(parents=True)
        return {
            "signal_date": str(signal_date),
            "execution_date": "2022-06-27",
            "eligible_symbols": ["B", "A"],
            "input_content_sha256": "input-sha",
            "data_commit": "dolt-rev",
            "lookback_days": 90,
        }

    def predictor(**kwargs):
        values = np.ones((5, 2, 10, 6), dtype=np.float32)
        values[:, :, 0, 0] = 100.0
        values[:, 0, -1, 3] = 110.0
        values[:, 1, -1, 3] = 120.0
        return {
            "predictions": values,
            "symbols": np.asarray(["B", "A"]),
            "runtime": {"prediction_content_sha256": "runtime-pred-sha"},
        }

    def backtest(weights, *, run_id, runs_dir, **kwargs):
        run_dir = Path(runs_dir) / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "report.html").write_text("<html>native</html>")
        (run_dir / "metrics.json").write_text("{}")
        return {
            "run_id": run_id,
            "run_dir": str(run_dir),
            "report_html": str(run_dir / "report.html"),
            "metrics": {},
            "result_hash": "backtest-hash",
        }

    result = run_research_pipeline(
        _Provider(),
        repo_root=repo,
        artifacts_root=tmp_path / "artifacts",
        runs_dir=tmp_path / "runs",
        start="2022-06-24",
        end="2022-06-24",
        signal_dates=["2022-06-24"],
        input_builder=input_builder,
        prediction_runner=predictor,
        backtest_runner=backtest,
        topk=1,
    )

    assert result["gate"]["completion_marker"] == "GOAL2_ENGINEERING_PASS"
    assert result["gate"]["formal_backtest_ready"] is False
    assert result["gate"]["real_assist_data_ready"] is False
    run_dir = Path(result["backtest"]["run_dir"])
    audit = json.loads((run_dir / "kronos_research_manifest.json").read_text())
    assert audit["prediction_hashes"]
    assert audit["signals_sha256"]
    assert audit["target_weights_sha256"]
    assert audit["backtest_result_hash"] == "backtest-hash"
    assert (run_dir / "kronos_signal_manifest.json").is_file()
    assert (run_dir / "target_weights.parquet").is_file()
