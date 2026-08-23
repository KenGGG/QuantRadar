from __future__ import annotations

import json

from scripts.kronos_data_audit import execute_audit_cli


def test_execute_audit_cli_prints_machine_readable_gate_summary(tmp_path, capsys):
    connection = object()
    provider = object()

    def runner(actual_connection, actual_provider, output_dir):
        assert actual_connection is connection
        assert actual_provider is provider
        assert output_dir == tmp_path / "audit"
        return {
            "output_dir": str(output_dir),
            "gates": {
                "kronos_signal_research_ready": True,
                "research_backtest_ready": True,
                "realistic_backtest_ready": True,
                "real_assist_data_ready": False,
                "csi300_pit_ready": False,
                "signal_research_ready": True,
                "formal_backtest_ready": False,
            },
        }

    exit_code = execute_audit_cli(
        connection,
        provider,
        tmp_path / "audit",
        audit_runner=runner,
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output == {
        "csi300_pit_ready": False,
        "formal_backtest_ready": False,
        "kronos_signal_research_ready": True,
        "output_dir": str(tmp_path / "audit"),
        "real_assist_data_ready": False,
        "research_backtest_ready": True,
        "realistic_backtest_ready": True,
        "signal_research_ready": True,
    }
