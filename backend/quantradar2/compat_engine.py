"""Application-owned JoinQuant legacy adjusted-price execution semantics."""
import math
import ast
import inspect
import textwrap
from decimal import Decimal
import numpy as np
from bullet_trade.core.engine import BacktestEngine
from bullet_trade.core.settings import get_settings
from bullet_trade.data.api import get_price, _get_default_provider

def _partial_fill_matcher():
    """Adapt the native matching lot size at its single explicit assignment.

    Keep native cash, fees, T+1, order and trade bookkeeping. Only orders already
    limited by bar volume use share-level partial fills. The installed engine
    and its globals remain untouched; unexpected source layout fails closed.
    """
    native=BacktestEngine._process_orders
    tree=ast.parse(textwrap.dedent(inspect.getsource(native)))
    assignments=[node for node in ast.walk(tree) if isinstance(node,ast.Assign)
                 and any(isinstance(t,ast.Name) and t.id=='min_trade_size' for t in node.targets)]
    if len(assignments)!=1 or not isinstance(assignments[0].value,ast.Constant) or assignments[0].value.value!=100:
        raise RuntimeError('Unsupported native matching lot-size layout')
    assignments[0].value=ast.Call(func=ast.Attribute(value=ast.Name(id='self',ctx=ast.Load()),
                attr='_matching_trade_size',ctx=ast.Load()),args=[ast.Name(id='order',ctx=ast.Load())],keywords=[])
    ast.fix_missing_locations(tree)
    namespace=dict(native.__globals__)
    exec(compile(tree,__file__+':partial_fill_matcher','exec'),namespace)
    return namespace['_process_orders']

class JoinQuantBacktestEngine(BacktestEngine):
    _process_orders=_partial_fill_matcher()

    def _matching_trade_size(self,order):
        return 1 if getattr(order,'_qr_volume_limited',False) else 100

    def load_strategy(self):
        result=super().load_strategy()
        # JQ logs preserve fees below one cent. An explicit strategy setting
        # can still override this default during initialize.
        get_settings().options.setdefault('equity_cash_decimals',None)
        get_settings().options['order_volume_ratio']=1.0
        return result

    def _calculate_order_amount(self,order,current_price):
        amount=super()._calculate_order_amount(order,current_price)
        order._qr_volume_limited=False
        if amount==0:return amount
        settings=get_settings()
        ratio=float(settings.options.get('order_volume_ratio',1.0))
        if not math.isfinite(ratio) or not 0<=ratio<=1:
            raise ValueError('order_volume_ratio must be between 0 and 1')
        # Execution-only bar volume: JQ daily matching is capped by the day's
        # complete adjusted volume. Do not expose this to strategy callbacks.
        provider=_get_default_provider()
        kwargs={'security':order.security,'end_date':self.context.current_dt,
                'frequency':'daily','fields':['volume'],'count':1,
                'fq':'pre' if self._legacy_adjusted() else 'none'}
        if self._legacy_adjusted():kwargs['pre_factor_ref_date']=settings.options.get('fq_ref_date')
        frame=provider.get_price(**kwargs)
        if frame.empty:self._fail_required_price(order.security,self.context.current_dt)
        volume=float(frame.iloc[-1]['volume'])
        if not math.isfinite(volume) or volume<0:
            self._fail_required_price(order.security,self.context.current_dt)
        limit=int(math.floor(volume*ratio))
        order._qr_volume_limited=abs(amount)>limit
        # Requested buys already obey the native 100-share lot rule. JQ can
        # partially fill that order with an odd quantity when volume binds
        # (exported 2020-11-13 ETF fill: 60,772 shares, not 60,700).
        if amount>0:return min(amount,limit)
        return -min(-amount,limit)

    def _round_to_tick(self,value,security,*,is_buy=None):
        if is_buy is not None:
            return super()._round_to_tick(value,security,is_buy=is_buy)
        step=self._tick_step_for_security(security)
        if step not in {.01,.001}:
            return super()._round_to_tick(value,security,is_buy=is_buy)
        decimals=max(0,-Decimal(str(step)).as_tuple().exponent)
        return float(np.round(float(value),decimals))

    def _legacy_adjusted(self):
        return not bool(get_settings().options.get('use_real_price', False))

    def _resolve_base_exec_price(self, security, current_dt, fq_mode):
        # JQ defaults to adjusted prices for orders as well as history. Native
        # BulletTrade uses raw orders but adjusted current-data price limits.
        return super()._resolve_base_exec_price(
            security, current_dt, 'pre' if self._legacy_adjusted() else fq_mode)

    def _apply_dividends_for_day(self, trade_day):
        # A fixed adjusted-price ledger already contains the action in prices.
        # Applying raw share changes again would double count a split.
        if not self._legacy_adjusted():
            return super()._apply_dividends_for_day(trade_day)

    def _update_positions(self):
        if not self._legacy_adjusted():return super()._update_positions()
        portfolio=self.context.portfolio
        for security, position in list(portfolio.positions.items()):
            frame=get_price(security=security,end_date=self.context.current_dt,
                            frequency='daily',fields=['close'],count=1,fq='pre')
            if frame.empty:
                self._fail_required_price(security,self.context.current_dt)
                continue
            self._assert_price_row_visible(frame,security,self.context.current_dt,daily=True)
            price=float(frame.iloc[-1]['close'])
            if not math.isfinite(price) or price<=0:
                self._fail_required_price(security,self.context.current_dt)
                continue
            position.update_price(price)
        self._mark_futures_positions()
        self._raise_if_backtest_data_error()
        portfolio.update_value()
