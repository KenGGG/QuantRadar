import os
import sys
from pathlib import Path
from types import SimpleNamespace


from bullet_trade.cli.main import apply_cli_overrides
from bullet_trade.core.globals import Logger


def test_main_env_file_triggers_refresh(monkeypatch):
    import bullet_trade.cli.main as main_mod
    import bullet_trade.utils.env_loader as env_loader

    called = {"load": None, "override": None, "load_calls": 0, "refresh": 0}

    def fake_load_env(env_file=None, override=False):
        called["load"] = env_file
        called["override"] = override
        called["load_calls"] += 1

    def fake_refresh():
        called["refresh"] += 1

    monkeypatch.setattr(env_loader, "load_env", fake_load_env)
    monkeypatch.setattr(main_mod, "_refresh_env_dependents", fake_refresh)
    monkeypatch.setattr(sys, "argv", ["bullet-trade", "--env-file", "custom.env"])

    exit_code = main_mod.main()

    assert exit_code == 0
    assert called["load"] == "custom.env"
    assert called["override"] is True
    assert called["load_calls"] == 1
    assert called["refresh"] == 1


def test_main_without_env_file_skips_refresh(monkeypatch):
    import bullet_trade.cli.main as main_mod
    import bullet_trade.utils.env_loader as env_loader

    called = {"load_calls": 0, "refresh": 0}

    def fake_load_env(env_file=None, override=False):
        called["load_calls"] += 1

    def fake_refresh():
        called["refresh"] += 1

    monkeypatch.setattr(env_loader, "load_env", fake_load_env)
    monkeypatch.setattr(main_mod, "_refresh_env_dependents", fake_refresh)
    monkeypatch.setattr(sys, "argv", ["bullet-trade"])

    exit_code = main_mod.main()

    assert exit_code == 0
    assert called["load_calls"] == 0
    assert called["refresh"] == 0


def test_apply_cli_overrides_updates_log_dir(tmp_path, monkeypatch):
    monkeypatch.delenv('LOG_DIR', raising=False)
    bootstrap_dir = tmp_path / "bootstrap"
    monkeypatch.setenv('LOG_DIR', str(bootstrap_dir))
    logger = Logger()

    log_dir = tmp_path / "cli_logs"
    args = SimpleNamespace(log_dir=str(log_dir), runtime_dir=None)

    overrides = apply_cli_overrides(args, logger=logger)

    assert overrides == {}
    assert os.environ['LOG_DIR'] == str(log_dir.resolve())
    handler = logger._file_handler
    assert handler is not None
    assert Path(handler.baseFilename).parent == log_dir.resolve()


def test_apply_cli_overrides_sets_runtime_override(tmp_path, monkeypatch):
    monkeypatch.delenv('RUNTIME_DIR', raising=False)
    runtime_dir = tmp_path / "runtime"
    args = SimpleNamespace(runtime_dir=str(runtime_dir), log_dir=None)

    overrides = apply_cli_overrides(args)

    expected = str(runtime_dir.resolve())
    assert overrides['runtime_dir'] == expected
    assert os.environ['RUNTIME_DIR'] == expected
