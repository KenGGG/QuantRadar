import os
from pathlib import Path
from types import SimpleNamespace


from bullet_trade.cli.live import run_live

_CREATED = []


class _DummyEngine:
    def __init__(self, *, strategy_file, broker_name=None, live_config=None):
        self.strategy_file = strategy_file
        self.broker_name = broker_name
        self.live_config = live_config or {}
        _CREATED.append(self)

    def run(self):
        return 0


def test_run_live_passes_runtime_override(monkeypatch, tmp_path):
    _CREATED.clear()
    monkeypatch.setattr('bullet_trade.cli.live.LiveEngine', _DummyEngine)
    monkeypatch.delenv('RUNTIME_DIR', raising=False)

    strategy = tmp_path / "strategy.py"
    strategy.write_text("from bullet_trade.api import *\n")
    runtime_dir = tmp_path / "runtime"

    args = SimpleNamespace(strategy_file=str(strategy), broker='simulator', runtime_dir=str(runtime_dir))
    exit_code = run_live(args)

    assert exit_code == 0
    dummy = _CREATED[-1]

    expected_runtime = str(runtime_dir.resolve())
    assert os.environ['RUNTIME_DIR'] == expected_runtime
    assert Path(dummy.strategy_file) == strategy.resolve()
    assert dummy.broker_name == 'simulator'
    assert dummy.live_config['runtime_dir'] == expected_runtime


def test_run_live_propagates_engine_exit_code(monkeypatch, tmp_path):
    _CREATED.clear()

    class _FailEngine(_DummyEngine):
        def run(self):
            return 2

    monkeypatch.setattr('bullet_trade.cli.live.LiveEngine', _FailEngine)
    strategy = tmp_path / "strategy.py"
    strategy.write_text("from bullet_trade.api import *\n")
    args = SimpleNamespace(strategy_file=str(strategy), broker='qmt', runtime_dir=None)
    exit_code = run_live(args)
    assert exit_code == 2
