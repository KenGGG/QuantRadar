"""Offline only: no network or real QMT trading requests."""
import asyncio
from types import SimpleNamespace
from unittest.mock import patch
from bullet_trade.server.config import ServerConfig
from bullet_trade.server.adapters.base import AccountRouter
from bullet_trade.server.adapters.big_qmt import build_big_qmt_bundle, BigQmtGatewayClient
from bullet_trade.server.app import ServerApplication

def test_broker_actions_rejected_before_gateway_call():
    config=ServerConfig(enable_data=True,enable_broker=False)
    router=AccountRouter(config.accounts)
    bundle=build_big_qmt_bundle(config,router)
    assert bundle.broker_adapter is None
    app=ServerApplication(config,router,bundle)
    actions=["broker.place_order","broker.cancel_order","broker.account","broker.orders","broker.resolve_submission"]
    with patch.object(BigQmtGatewayClient,"post") as post, patch.object(BigQmtGatewayClient,"get") as get:
        for action in actions:
            try:
                asyncio.run(app.handle_request(SimpleNamespace(),action,{}))
            except RuntimeError:
                pass
            else:
                raise AssertionError("Broker action accepted: "+action)
        post.assert_not_called()
        get.assert_not_called()
    assert app.active_features()==["data"]
