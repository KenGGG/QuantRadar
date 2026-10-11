"""Small explicit QMT compatibility layer, without modifying native engine."""
from bullet_trade.data.providers.remote_qmt import RemoteQmtProvider

class ResearchQmtProvider(RemoteQmtProvider):
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
        return super().get_price(security, *args, **kwargs)
