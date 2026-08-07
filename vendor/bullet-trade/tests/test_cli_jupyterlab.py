import argparse
import sys
from pathlib import Path

import bullet_trade.cli.jupyterlab as jl


def test_load_or_init_settings_creates_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("BULLET_TRADE_HOME", str(tmp_path))
    settings, first_run, settings_path = jl.load_or_init_settings()
    assert first_run is True
    assert settings.root_dir == Path(tmp_path) / "bullet-trade"
    assert settings.env_path == settings.root_dir / ".env"
    assert settings_path.exists()
    # 再次加载不应视为首次
    settings_again, first_run_again, _ = jl.load_or_init_settings()
    assert first_run_again is False
    assert settings_again.root_dir == settings.root_dir


def test_run_lab_blocks_public_without_auth(monkeypatch, tmp_path):
    monkeypatch.setenv("BULLET_TRADE_HOME", str(tmp_path))
    monkeypatch.setitem(sys.modules, "jupyterlab", type("x", (), {})())
    monkeypatch.setattr(jl, "_check_port_available", lambda h, p: (True, None))
    args = argparse.Namespace(
        ip="0.0.0.0",
        port=None,
        notebook_dir=None,
        env_file=None,
        no_browser=False,
        browser=False,
        token=None,
        no_token=False,
        password=None,
        certfile=None,
        keyfile=None,
        allow_origin=None,
        diagnose=False,
        command="lab",
    )
    rc = jl.run_lab(args)
    assert rc == 1  # 非 loopback 且无密码/证书被拒绝


def test_run_lab_builds_command_and_uses_root_env(monkeypatch, tmp_path):
    monkeypatch.setenv("BULLET_TRADE_HOME", str(tmp_path))
    monkeypatch.setitem(sys.modules, "jupyterlab", type("x", (), {})())
    monkeypatch.setattr(jl, "_check_port_available", lambda h, p: (True, None))

    calls = {}

    def fake_run(cmd, cwd=None, env=None):
        calls["cmd"] = cmd
        calls["cwd"] = cwd
        calls["env"] = env

        class R:
            returncode = 0

        return R()

    monkeypatch.setattr(jl.subprocess, "run", fake_run)
    args = argparse.Namespace(
        ip=None,
        port=18080,
        notebook_dir=None,
        env_file=None,
        no_browser=True,
        browser=False,
        token="testtoken",
        no_token=False,
        password=None,
        certfile=None,
        keyfile=None,
        allow_origin=None,
        diagnose=False,
        command="lab",
    )
    rc = jl.run_lab(args)
    assert rc == 0
    assert "--ServerApp.port=18080" in calls["cmd"]
    assert any(str(tmp_path / "bullet-trade") in part for part in calls["cmd"])
    assert calls["cwd"] == str(tmp_path / "bullet-trade")
    assert calls["env"].get("JUPYTER_CONFIG_DIR") == str(tmp_path / ".bullet-trade" / "jupyter-config")
    # env 与设置文件应已创建
    settings_path = tmp_path / ".bullet-trade" / "setting.json"
    assert settings_path.exists()
    assert (tmp_path / "bullet-trade" / ".env").exists()
