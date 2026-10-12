"""Application-owned JoinQuant legacy adjusted-price execution semantics."""
import math
from decimal import Decimal
import numpy as np
from bullet_trade.core.engine import BacktestEngine
from bullet_trade.core.settings import get_settings
from bullet_trade.data.api import get_price, _get_default_provider

class JoinQuantBacktestEngine(BacktestEngine):
    def load_strategy(self):
        result=super().load_strategy()
        # JQ logs preserve fees below one cent. An explicit strategy setting
        # can still override this default during initialize.
        get_settings().options.setdefault('equity_cash_decimals',None)
        get_settings().options['order_volume_ratio']=1.0
        return result

    def _calculate_order_amount(self,order,current_price):
        amount=super()._calculate_order_amount(order,current_price)
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
        if amount>0:return min(amount,(limit//100)*100)
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
