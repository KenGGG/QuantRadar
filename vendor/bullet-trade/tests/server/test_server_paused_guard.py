import asyncio
from types import SimpleNamespace

import pytest

from bullet_trade.server.app import ServerApplication


class _FakeDataAdapter:
    def __init__(self, paused: bool):
        self.paused = paused
        self.calls = 0

    async def get_live_current(self, payload):
        self.calls += 1
        return {"paused": self.paused, "last_price": 10.0}


def _build_app(paused: bool) -> ServerApplication:
    app = object.__new__(ServerApplication)
    app.adapters = SimpleNamespace(data_adapter=_FakeDataAdapter(paused), broker_adapter=None)
    return app


@pytest.mark.asyncio
async def test_paused_security_warns_but_not_raise(caplog):
    app = _build_app(paused=True)
    with caplog.at_level("WARNING"):
        await app._maybe_reject_when_paused({"security": "000001.XSHE"})
    assert any("停牌" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_active_security_passes_through():
    app = _build_app(paused=False)
    await app._maybe_reject_when_paused({"security": "000002.XSHE"})
    assert app.adapters.data_adapter.calls == 1
