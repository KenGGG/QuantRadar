"""Small explicit QMT compatibility layer, without modifying native engine."""
from bullet_trade.data.providers.remote_qmt import RemoteQmtProvider
from datetime import date, timedelta
import numpy as np
import pandas as pd

class ResearchQmtProvider(RemoteQmtProvider):
    consistent_fund_reference = True

    def _fund_actions(self, security, reference):
        cache=self.__dict__.setdefault('_fund_adjustment_cache',{})
        key=(security,str(reference))
        if key in cache:return cache[key]
        info=self.get_security_info(security)
        kind=info.get('type') if isinstance(info,dict) else getattr(info,'type',None)
        if kind not in {'fund','etf'}:
            cache[key]=None
            return None
        start=info.get('start_date') if isinstance(info,dict) else getattr(info,'start_date',None)
        events=self.get_split_dividend(security,str(start or '1990-01-01'),str(reference))
        if not isinstance(events,list):raise ValueError('QMT fund action coverage unavailable')
        result=[];post_factor=1.0
        for event in sorted(events,key=lambda x:x['date']):
            event_day=pd.Timestamp(event['date']).normalize()
            prior=super().get_price(security,end_date=str((event_day-timedelta(days=1)).date()),
                    count=1,frequency='daily',fields=['close'],fq='none',skip_paused=True)
            current=super().get_price(security,start_date=str(event_day.date()),end_date=str(event_day.date()),
                    frequency='daily',fields=['pre_close'],fq='none',skip_paused=False)
            if prior.empty or len(current)!=1:raise ValueError('QMT fund action reference missing: '+security)
            before=float(prior.iloc[-1]['close']);after=float(current.iloc[0]['pre_close'])
            if not np.isfinite([before,after]).all() or min(before,after)<=0:
                raise ValueError('Invalid QMT fund ex-reference: '+security)
            # JQ's exported cumulative post factors use six decimal places
            # (e.g. 2.046192 and 5.001927). Pre factors are their ratios.
            next_factor=round(post_factor*before/after,6)
            if next_factor<=0:raise ValueError('Invalid cumulative fund adjustment factor')
            result.append({'date':str(event_day.date()),'previous_close':before,
                           'exchange_pre_close':after,'post_factor':next_factor,
                           'multiplier':post_factor/next_factor})
            post_factor=next_factor
        cache[key]=result
        return result
    def get_trade_days(self, start_date=None, end_date=None, count=None):
        # BigQMT defaults count=None to 250 even for bounded intervals.
        # Calendar days bound sessions without imposing a fixed maximum span.
        if start_date is not None and end_date is not None and count is None:
            from pandas import Timestamp
            start, end = Timestamp(start_date).normalize(), Timestamp(end_date).normalize()
            count = max(1, (end - start).days + 1)
            days = super().get_trade_days(start_date, end_date, count)
            if any(not start <= day <= end for day in days) or any(
                left >= right for left, right in zip(days, days[1:])
            ):
                raise ValueError('Invalid bounded trading calendar: range/order/duplicates')
            return days
        return super().get_trade_days(start_date, end_date, count)

    def get_price(self, security, *args, **kwargs):
        fields = kwargs.get("fields")
        # The native current-data path requests this exact field set. BigQMT
        # rejects historical limits. Omit them so the engine uses its existing
        # code/previous-close estimate; never claim those estimates are QMT data.
        if fields == ["open", "close", "high_limit", "low_limit", "paused"]:
            kwargs = dict(kwargs, fields=["open", "close", "paused"])
        # Rebuild fund pre-adjustment from QMT's exchange ex-reference price,
        # rather than a rounded theoretical price from the share split ratio.
        # Use raw bars before rounding, so three-decimal OHLC remain reproducible.
        # The research/native metadata/volume source remains QMT exclusively.
        if not args and kwargs.get('fq','pre')=='pre':
            reference=pd.Timestamp(kwargs.get('pre_factor_ref_date') or date.today()).normalize()
            coverage=max(reference.date(),pd.Timestamp(kwargs.get('end_date') or date.today()).date())
            actions=self._fund_actions(security,coverage)
            if actions is not None:
                raw_kwargs=dict(kwargs,fq='none',pre_factor_ref_date=None)
                frame=super().get_price(security,**raw_kwargs).copy()
                factor=np.ones(len(frame))
                index=pd.DatetimeIndex(frame.index).normalize()
                for action in actions:
                    event_day=pd.Timestamp(action['date'])
                    if event_day<=reference:factor[index<event_day]*=action['multiplier']
                    else:factor[index>=event_day]/=action['multiplier']
                for column in ['open','high','low','close','pre_close','avg']:
                    if column in frame:frame[column]=np.round(frame[column].to_numpy(dtype=float)*factor,3)
                if 'volume' in frame:frame['volume']=np.round(frame.volume.to_numpy(dtype=float)/factor)
                return frame
        return super().get_price(security, *args, **kwargs)
