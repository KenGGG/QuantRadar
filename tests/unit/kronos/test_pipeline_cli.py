from __future__ import annotations

import json

from scripts.kronos_research_pipeline import execute_pipeline_cli

from quantradar.kronos.universe_spec import Universe


def _passed_gate():
    return {
        "signal_run_dir": "/tmp/signal",
        "backtest": {"run_dir": "/tmp/run"},
        "gate": {
            "engineering_ready": True,
            "completion_marker": "GOAL2_ENGINEERING_PASS",
            "kronos_signal_research_ready": True,
            "realistic_backtest_ready": True,
            "real_assist_data_ready": False,
            "csi300_pit_ready": False,
            "formal_backtest_ready": True,
            "signal_research_ready": True,
        },
    }


def _blocked_gate():
    return {
        "signal_run_dir": "/tmp/signal",
        "backtest": {"run_dir": "/tmp/run"},
        "gate": {
            "engineering_ready": False,
            "completion_marker": None,
            "kronos_signal_research_ready": False,
            "realistic_backtest_ready": False,
            "real_assist_data_ready": False,
            "csi300_pit_ready": False,
            "formal_backtest_ready": False,
            "signal_research_ready": False,
        },
    }


def test_cli_returns_zero_only_for_engineering_pass(capsys, tmp_path):
    def passed(provider, **kwargs):
        return _passed_gate()

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
    assert output["formal_backtest_ready"] is True
    assert output["real_assist_data_ready"] is False


def test_cli_returns_nonzero_without_pass_marker(capsys, tmp_path):
    def blocked(provider, **kwargs):
        return _blocked_gate()

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


def test_cli_forwards_universe_to_pipeline_runner(capsys, tmp_path):
    captured = {}

    def spy(provider, **kwargs):
        captured.update(kwargs)
        return _passed_gate()

    execute_pipeline_cli(
        object(),
        repo_root=tmp_path,
        artifacts_root=tmp_path / "artifacts",
        runs_dir=tmp_path / "runs",
        start="2022-06-24",
        end="2022-06-24",
        topk=20,
        universe=Universe.CSI300_PIT,
        pipeline_runner=spy,
    )
    assert captured.get("universe") is Universe.CSI300_PIT
