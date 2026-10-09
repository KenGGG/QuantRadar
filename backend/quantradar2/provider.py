"""Small explicit QMT compatibility layer, without modifying native engine."""
from bullet_trade.data.providers.remote_qmt import RemoteQmtProvider

class ResearchQmtProvider(RemoteQmtProvider):
    def get_price(self, security, *args, **kwargs):
        fields = kwargs.get("fields")
        # The native current-data path requests this exact field set. BigQMT
        # rejects historical limits. Omit them so the engine uses its existing
        # code/previous-close estimate; never claim those estimates are QMT data.
        if fields == ["open", "close", "high_limit", "low_limit", "paused"]:
            kwargs = dict(kwargs, fields=["open", "close", "paused"])
        return super().get_price(security, *args, **kwargs)
