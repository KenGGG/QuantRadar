import os

from bullet_trade.core.globals import g
from bullet_trade.core.live_runtime import init_live_runtime, save_g, start_g_autosave, stop_g_autosave


def test_g_persist_cycle(tmp_path):
    runtime = tmp_path / "rt"
    init_live_runtime(str(runtime))
    g.foo = 123
    save_g()

    # 变更并再次初始化，应恢复为持久化的值
    g.foo = 0
    init_live_runtime(str(runtime))
    assert g.foo == 123


def test_autosave_thread(tmp_path):
    runtime = tmp_path / "rt2"
    init_live_runtime(str(runtime))
    g.bar = 456
    start_g_autosave(interval_sec=1)
    # 粗略等待 autosave 执行一次
    import time

    time.sleep(1.5)
    stop_g_autosave()
    path = os.path.join(str(runtime), "g.pkl")
    assert os.path.exists(path)

