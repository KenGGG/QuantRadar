from bullet_trade.core.live_engine import LiveEngine
from bullet_trade.core.models import Order


def test_live_engine_build_order_remark_uses_strategy_name(tmp_path):
    strategy_file = tmp_path / "demo_strategy.py"
    strategy_file.write_text("def initialize(context):\n    pass\n")

    engine = LiveEngine(
        strategy_file=str(strategy_file),
        live_config={"strategy_name": "Alpha-1"},
    )
    order = Order(order_id="oid-123", security="000001.XSHE", amount=100)

    remark = engine._prepare_order_metadata(order)
    assert remark is not None
    assert remark.startswith("bt:alpha-1:")
    assert len(remark) <= 24
    assert order.extra.get("order_remark") == remark
    assert order.extra.get("strategy_name") == "Alpha-1"
