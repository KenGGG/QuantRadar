from __future__ import annotations

from scripts.kronos_gpu_smoke import execute_gpu_smoke_cli


def test_cli_returns_success_only_for_real_runtime_pass(tmp_path, capsys) -> None:
    def passing_runner(provider, **kwargs):
        return {
            "output_dir": str(tmp_path),
            "gate": {
                "runtime_ready": True,
                "status": "PASS",
                "completion_marker": "KRONOS_BASE_GPU_RUNTIME_PASS",
                "reasons": [],
            },
        }

    code = execute_gpu_smoke_cli(object(), tmp_path, tmp_path, smoke_runner=passing_runner)

    assert code == 0
    assert "KRONOS_BASE_GPU_RUNTIME_PASS" in capsys.readouterr().out


def test_cli_returns_blocked_exit_code_without_success_marker(tmp_path, capsys) -> None:
    def blocked_runner(provider, **kwargs):
        return {
            "output_dir": str(tmp_path),
            "gate": {
                "runtime_ready": False,
                "status": "BLOCKED",
                "completion_marker": None,
                "reasons": ["CUDA unavailable"],
            },
        }

    code = execute_gpu_smoke_cli(object(), tmp_path, tmp_path, smoke_runner=blocked_runner)

    assert code == 2
    assert "KRONOS_BASE_GPU_RUNTIME_PASS" not in capsys.readouterr().out
