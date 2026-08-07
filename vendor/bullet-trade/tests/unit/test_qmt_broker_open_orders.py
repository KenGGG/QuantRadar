import pytest

from bullet_trade.broker.qmt import QmtBroker


@pytest.mark.unit
def test_qmt_broker_get_open_orders_filters_status(monkeypatch):
    broker = QmtBroker(account_id="demo")
    broker._connected = True

    monkeypatch.setattr(
        broker,
        "sync_orders",
        lambda: [
            {"order_id": "1", "status": "submitted"},
            {"order_id": "2", "status": "filled"},
        ],
    )

    orders = broker.get_open_orders()
    ids = {item.get("order_id") for item in orders}
    assert "1" in ids
    assert "2" not in ids
