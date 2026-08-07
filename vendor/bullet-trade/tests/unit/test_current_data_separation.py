from datetime import datetime
from types import SimpleNamespace


from bullet_trade.core.settings import reset_settings
from bullet_trade.core.globals import g
from bullet_trade.data.api import get_current_data, set_current_context


def test_current_data_backtest_default():
    reset_settings()
    cd = get_current_data()
    # 默认无 xtdata 环境，非显式设置，应走 BacktestCurrentData
    assert type(cd).__name__ in ("BacktestCurrentData", "EmptyCurrentData")


def test_current_data_live_selected_without_xtdata(monkeypatch):
    reset_settings()
    g.live_trade = True

    class _StubProvider:
        requires_live_data = False

        def get_live_current(self, security):
            return {}

    ctx = SimpleNamespace(current_dt=datetime(2025, 1, 2, 9, 30))
    set_current_context(ctx)
    monkeypatch.setattr("bullet_trade.data.api._provider", _StubProvider(), raising=False)
    cd = get_current_data()
    # 实盘模式下返回 LiveCurrentData；访问时如 provider 无 live 快照则回退
    assert type(cd).__name__ == "LiveCurrentData"
    # 访问一个标的不应报错
    _ = cd['000001.XSHE']
    set_current_context(None)
    g.live_trade = False


def test_live_current_data_prefers_provider_tick(monkeypatch):
    reset_settings()
    g.live_trade = True

    class DummyProvider:
        requires_live_data = False

        def get_live_current(self, security):
            return {
                "last_price": 12.34,
                "high_limit": 13.0,
                "low_limit": 11.0,
                "paused": False,
            }

    ctx = SimpleNamespace(current_dt=datetime(2025, 1, 2, 10, 0))
    set_current_context(ctx)
    monkeypatch.setattr("bullet_trade.data.api._provider", DummyProvider(), raising=False)
    cd = get_current_data()
    snap = cd["000001.XSHE"]
    assert snap.last_price == 12.34
    assert snap.high_limit == 13.0
    assert snap.low_limit == 11.0
    set_current_context(None)
    g.live_trade = False
