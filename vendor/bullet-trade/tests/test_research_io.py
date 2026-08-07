import json
import logging
from pathlib import Path

import pytest

from bullet_trade.core.globals import log
from bullet_trade.research.io import read_file, write_file


def _write_settings(tmp_path: Path, root_dir: Path) -> None:
    cfg_dir = tmp_path / ".bullet-trade"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    settings = {"root_dir": str(root_dir)}
    (cfg_dir / "setting.json").write_text(json.dumps(settings), encoding="utf-8")


def test_uninitialized_prompts_lab(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("BULLET_TRADE_HOME", str(tmp_path))
    caplog.set_level(logging.WARNING, logger=log.logger.name)
    with pytest.raises(FileNotFoundError) as exc:
        read_file("foo.txt")
    message = str(exc.value)
    assert "bullet-trade lab" in message
    assert str(tmp_path / "bullet-trade") in message
    assert any("bullet-trade lab" in record.message for record in caplog.records)


def test_uninitialized_logs_warning(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("BULLET_TRADE_HOME", str(tmp_path))
    caplog.set_level(logging.WARNING, logger=log.logger.name)
    with pytest.raises(FileNotFoundError):
        write_file("bar.txt", "x")
    warns = [r for r in caplog.records if "bullet-trade lab" in r.message]
    assert warns, "未初始化时应记录警告提示用户运行 bullet-trade lab"
    assert all(r.levelno == logging.WARNING for r in warns)


def test_write_and_read_with_logging(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("BULLET_TRADE_HOME", str(tmp_path))
    root_dir = tmp_path / "bullet-trade-root"
    root_dir.mkdir(parents=True, exist_ok=True)
    _write_settings(tmp_path, root_dir)

    caplog.set_level(logging.INFO, logger=log.logger.name)
    write_file("logs/out.csv", "a", append=False)
    write_file("logs/out.csv", b"b", append=True)
    content = read_file("logs/out.csv")

    assert content == b"ab"
    assert any("logs/out.csv" in record.message and str(root_dir) in record.message for record in caplog.records)


def test_rejects_escape_path(monkeypatch, tmp_path):
    monkeypatch.setenv("BULLET_TRADE_HOME", str(tmp_path))
    root_dir = tmp_path / "root"
    root_dir.mkdir(parents=True, exist_ok=True)
    _write_settings(tmp_path, root_dir)

    with pytest.raises(ValueError) as exc:
        write_file("../bad.txt", "x")
    assert "../bad.txt" in str(exc.value)


def test_default_root_without_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("BULLET_TRADE_HOME", str(tmp_path))
    default_root = tmp_path / "bullet-trade"
    default_root.mkdir(parents=True, exist_ok=True)

    write_file("foo.txt", "hello", append=False)
    assert read_file("foo.txt") == b"hello"


def test_engine_injects_read_write(monkeypatch, tmp_path):
    monkeypatch.setenv("BULLET_TRADE_HOME", str(tmp_path))
    root_dir = tmp_path / "bullet-trade"
    root_dir.mkdir(parents=True, exist_ok=True)
    _write_settings(tmp_path, root_dir)

    def init(ctx):
        # 验证注入的全局函数可用
        write_file("inject.txt", "yes")
        assert read_file("inject.txt") == b"yes"

    from bullet_trade.core.engine import BacktestEngine

    engine = BacktestEngine(initialize=init, start_date="2025-01-01", end_date="2025-01-02")
    engine.load_strategy()  # 会注入全局并调用初始化函数所在模块
    # 初始化函数在 load_strategy 之外不会被调用；直接手动调用以验证注入
    engine.initialize_func(engine.context or None)
