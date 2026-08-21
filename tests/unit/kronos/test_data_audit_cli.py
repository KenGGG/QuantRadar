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
                "signal_research_ready": True,
                "formal_backtest_ready": False,
                "real_assist_data_ready": False,
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
        "formal_backtest_ready": False,
        "output_dir": str(tmp_path / "audit"),
        "real_assist_data_ready": False,
        "signal_research_ready": True,
    }
