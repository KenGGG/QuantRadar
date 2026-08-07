import pytest

from bullet_trade.core.engine import BacktestEngine
from bullet_trade.core.settings import (
    reset_settings,
    set_slippage,
    PriceRelatedSlippage,
    StepRelatedSlippage,
    FixedSlippage,
)


@pytest.fixture(autouse=True)
def _reset_settings():
    reset_settings()
    yield
    reset_settings()


def test_price_related_slippage_global(monkeypatch):
    set_slippage(PriceRelatedSlippage(0.002))

    monkeypatch.setattr(
        'bullet_trade.core.engine.get_security_info',
        lambda _: {'type': 'stock', 'category': 'stock'},
    )
    engine = BacktestEngine()
    trade_price = engine._apply_slippage_price(10.0, True, '000001.XSHE')
    assert trade_price == pytest.approx(10.01)


def test_step_slippage_ref_priority(monkeypatch):
    set_slippage(PriceRelatedSlippage(0.003), type='stock')
    set_slippage(StepRelatedSlippage(2), type='futures', ref='RB1809.XSGE')

    monkeypatch.setattr(
        'bullet_trade.core.engine.get_security_info',
        lambda code: {'type': 'futures', 'category': 'futures', 'tick_size': 1.0},
    )
    engine = BacktestEngine()
    trade_price = engine._apply_slippage_price(3000.0, True, 'RB1809.XSGE')
    assert trade_price == pytest.approx(3001.0)


def test_money_market_fund_slippage_zero(monkeypatch):
    set_slippage(PriceRelatedSlippage(0.005))

    monkeypatch.setattr(
        'bullet_trade.core.engine.get_security_info',
        lambda _: {'type': 'fund', 'subtype': 'mmf', 'category': 'money_market_fund', 'slippage': 0.01},
    )
    engine = BacktestEngine()
    trade_price = engine._apply_slippage_price(1.001, True, '511880.XSHG')
    assert trade_price == pytest.approx(1.001)


def test_default_slippage_fallback(monkeypatch):
    # 未显式设置滑点时，使用 info.slippage 或默认值
    monkeypatch.setattr(
        'bullet_trade.core.engine.get_security_info',
        lambda _: {'type': 'stock', 'category': 'stock', 'slippage': 0.002},
    )
    engine = BacktestEngine()
    trade_price = engine._apply_slippage_price(10.0, True, '000001.XSHE')
    assert trade_price == pytest.approx(10.01)

