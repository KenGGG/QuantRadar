from types import SimpleNamespace
from unittest.mock import Mock, patch
import pandas as pd
from quantradar2 import compat_engine as compat

def engine(monkeypatch, real=False):
    monkeypatch.setattr(compat,'get_settings',lambda:SimpleNamespace(options={'use_real_price':real}))
    e=object.__new__(compat.JoinQuantBacktestEngine)
    return e

def test_execution_uses_same_adjustment_family_as_current_data(monkeypatch):
    e=engine(monkeypatch)
    with patch.object(compat.BacktestEngine,'_resolve_base_exec_price',return_value=.559) as native:
        assert e._resolve_base_exec_price('513100.XSHG',pd.Timestamp('2019-07-08 09:30'),'none')==.559
        assert native.call_args.args[-1]=='pre'
    e=engine(monkeypatch,True)
    with patch.object(compat.BacktestEngine,'_resolve_base_exec_price',return_value=2.791) as native:
        assert e._resolve_base_exec_price('513100.XSHG',pd.Timestamp('2019-07-08 09:30'),'none')==2.791
        assert native.call_args.args[-1]=='none'

def test_adjusted_ledger_does_not_double_count_actions(monkeypatch):
    e=engine(monkeypatch)
    with patch.object(compat.BacktestEngine,'_apply_dividends_for_day') as native:
        e._apply_dividends_for_day(pd.Timestamp('2022-01-14'))
        native.assert_not_called()
    e=engine(monkeypatch,True)
    with patch.object(compat.BacktestEngine,'_apply_dividends_for_day') as native:
        e._apply_dividends_for_day(pd.Timestamp('2022-01-14'))
        native.assert_called_once()

def test_price_rounding_matches_exported_half_tick_fills(monkeypatch):
    e=engine(monkeypatch)
    e._tick_step_for_security=lambda code:.001
    assert e._round_to_tick(2.85+.0005,'518880.XSHG')==2.851
    assert e._round_to_tick(3.091-.0005,'518880.XSHG')==3.09
    assert e._round_to_tick(.558+.0005,'513100.XSHG')==.558
    assert e._round_to_tick(.524+.0005,'159949.XSHE')==.524

def test_cash_fee_default_keeps_subcent_precision(monkeypatch):
    e=engine(monkeypatch)
    settings=SimpleNamespace(options={})
    monkeypatch.setattr(compat,'get_settings',lambda:settings)
    monkeypatch.setattr('bullet_trade.core.engine.get_settings',lambda:settings)
    with patch.object(compat.BacktestEngine,'load_strategy'):
        e.load_strategy()
    assert settings.options['equity_cash_decimals'] is None
    assert e._round_equity_cash(148.48008)==148.48008
    assert settings.options['order_volume_ratio']==1.0

def test_volume_cap_keeps_partial_position_and_buy_lots(monkeypatch):
    e=engine(monkeypatch)
    e.context=SimpleNamespace(current_dt=pd.Timestamp('2021-04-07 09:30'))
    source=SimpleNamespace(get_price=Mock(return_value=pd.DataFrame({'volume':[269036]})))
    monkeypatch.setattr(compat,'_get_default_provider',lambda:source)
    with patch.object(compat.BacktestEngine,'_calculate_order_amount',return_value=-1600000):
        assert e._calculate_order_amount(SimpleNamespace(security='512890.XSHG'),.708)==-269036
    assert source.get_price.call_args.kwargs['fq']=='pre'
    with patch.object(compat.BacktestEngine,'_calculate_order_amount',return_value=1600000):
        assert e._calculate_order_amount(SimpleNamespace(security='512890.XSHG'),.708)==269000

def test_adjusted_valuation_and_strict_invalid_data(monkeypatch):
    e=engine(monkeypatch)
    position=SimpleNamespace(update_price=Mock())
    portfolio=SimpleNamespace(positions={'513100.XSHG':position},update_value=Mock())
    e.context=SimpleNamespace(portfolio=portfolio,current_dt=pd.Timestamp('2019-07-08 15:00'))
    e._assert_price_row_visible=Mock();e._mark_futures_positions=Mock();e._raise_if_backtest_data_error=Mock()
    e._fail_required_price=Mock(side_effect=ValueError('missing price'))
    price=Mock(return_value=pd.DataFrame({'close':[.555]},index=[e.context.current_dt]))
    monkeypatch.setattr(compat,'get_price',price)
    e._update_positions()
    assert price.call_args.kwargs['fq']=='pre'
    position.update_price.assert_called_once_with(.555)
    price.return_value=pd.DataFrame()
    import pytest
    with pytest.raises(ValueError,match='missing price'):e._update_positions()
