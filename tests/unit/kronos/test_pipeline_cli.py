from __future__ import annotations

import json

from scripts.kronos_research_pipeline import execute_pipeline_cli


def test_cli_returns_zero_only_for_engineering_pass(capsys, tmp_path):
    def passed(provider, **kwargs):
        return {
            "signal_run_dir": str(tmp_path / "signal"),
            "backtest": {"run_dir": str(tmp_path / "run")},
            "gate": {
                "engineering_ready": True,
                "completion_marker": "GOAL2_ENGINEERING_PASS",
                "formal_backtest_ready": False,
                "real_assist_data_ready": False,
            },
        }

    code = execute_pipeline_cli(
        object(),
        repo_root=tmp_path,
        artifacts_root=tmp_path / "artifacts",
        runs_dir=tmp_path / "runs",
        start="2022-06-24",
        end="2022-06-24",
        topk=20,
        pipeline_runner=passed,
    )
    assert code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["completion_marker"] == "GOAL2_ENGINEERING_PASS"
    assert output["formal_backtest_ready"] is False


def test_cli_returns_nonzero_without_pass_marker(capsys, tmp_path):
    def blocked(provider, **kwargs):
        return {
            "signal_run_dir": str(tmp_path / "signal"),
            "backtest": {"run_dir": str(tmp_path / "run")},
            "gate": {
                "engineering_ready": False,
                "completion_marker": None,
                "formal_backtest_ready": False,
                "real_assist_data_ready": False,
            },
        }

    assert execute_pipeline_cli(
        object(),
        repo_root=tmp_path,
        artifacts_root=tmp_path / "artifacts",
        runs_dir=tmp_path / "runs",
        start="2022-06-24",
        end="2022-06-24",
        topk=20,
        pipeline_runner=blocked,
    ) == 2
