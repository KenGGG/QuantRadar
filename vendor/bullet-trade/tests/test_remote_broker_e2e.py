import asyncio
import os
from typing import Dict

import pytest

from bullet_trade.broker import RemoteQmtBroker

"""
远程 QMT server 端到端验证。

必须在 `bullet-trade/.env`（或外部 env）中配置下列变量，并显式启用测试：

    REMOTE_QMT_TEST_ENABLED=1              # 开启真实连接测试
    QMT_SERVER_HOST=your.remote.host
    QMT_SERVER_PORT=58620
    QMT_SERVER_TOKEN=secret-token
    QMT_SERVER_ACCOUNT_KEY=main            # 可选
    QMT_SERVER_SUB_ACCOUNT=demo@main       # 可选
    QMT_SERVER_TLS_CERT=/path/to/ca.pem    # 可选，启用 TLS 时使用

    REMOTE_QMT_TEST_LIMIT_SYMBOL=000001.XSHE
    REMOTE_QMT_TEST_LIMIT_PRICE=10.0
    REMOTE_QMT_TEST_LIMIT_AMOUNT=100
    REMOTE_QMT_TEST_MARKET_SYMBOL=000002.XSHE
    REMOTE_QMT_TEST_MARKET_AMOUNT=100
    REMOTE_QMT_TEST_ACCOUNT=remote-e2e     # 可选，日志中区分来源

测试流程：
1. 连接远程 server，获取账户资产和持仓；
2. 发送限价单与市价单（均为买入，amount 可调），验证订单 ID；
3. 轮询订单状态（异步接口）；
4. `sync_orders` 校验订单列表（同步接口）；
5. 撤销限价单，保证测试对真实账户的影响最小。

pytest bullet-trade/tests/test_remote_broker_e2e.py -m "e2e and requires_network"
"""


def _enabled() -> bool:
    flag = os.getenv("REMOTE_QMT_TEST_ENABLED", "").strip().lower()
    return flag in {"1", "true", "yes", "on"}


def _required_env(keys) -> Dict[str, str]:
    values: Dict[str, str] = {}
    missing = []
    for key in keys:
        value = os.getenv(key)
        if not value:
            missing.append(key)
        else:
            values[key] = value
    if missing:
        pytest.skip(f"缺少远程测试必需环境变量: {', '.join(missing)}")
    return values


@pytest.mark.asyncio
@pytest.mark.requires_network
@pytest.mark.e2e
async def test_remote_broker_against_real_server():
    if not _enabled():
        pytest.skip("REMOTE_QMT_TEST_ENABLED 未开启，跳过远程 server 端到端测试")

    core_env = _required_env(["QMT_SERVER_HOST", "QMT_SERVER_TOKEN"])
    port = int(os.getenv("QMT_SERVER_PORT", "58620"))
    tls_cert = os.getenv("QMT_SERVER_TLS_CERT")
    config = {
        "host": core_env["QMT_SERVER_HOST"],
        "port": port,
        "token": core_env["QMT_SERVER_TOKEN"],
        "account_key": os.getenv("QMT_SERVER_ACCOUNT_KEY"),
        "sub_account_id": os.getenv("QMT_SERVER_SUB_ACCOUNT"),
        "tls_cert": tls_cert,
    }

    order_env = _required_env(
        [
            "REMOTE_QMT_TEST_LIMIT_SYMBOL",
            "REMOTE_QMT_TEST_LIMIT_PRICE",
            "REMOTE_QMT_TEST_MARKET_SYMBOL",
        ]
    )
    limit_amount = int(os.getenv("REMOTE_QMT_TEST_LIMIT_AMOUNT", "100"))
    market_amount = int(os.getenv("REMOTE_QMT_TEST_MARKET_AMOUNT", str(limit_amount)))

    broker = RemoteQmtBroker(
        account_id=os.getenv("REMOTE_QMT_TEST_ACCOUNT", "remote-e2e"),
        config=config,
    )

    try:
        assert broker.connect() is True
        account_info = broker.get_account_info()
        assert isinstance(account_info, dict)
        assert "available_cash" in account_info

        positions = broker.get_positions()
        assert isinstance(positions, list)

        limit_order_id, market_order_id = await asyncio.gather(
            broker.buy(
                order_env["REMOTE_QMT_TEST_LIMIT_SYMBOL"],
                limit_amount,
                price=float(order_env["REMOTE_QMT_TEST_LIMIT_PRICE"]),
            ),
            broker.buy(order_env["REMOTE_QMT_TEST_MARKET_SYMBOL"], market_amount, price=None),
        )
        assert isinstance(limit_order_id, str) and limit_order_id
        assert isinstance(market_order_id, str) and market_order_id

        limit_status = await broker.get_order_status(limit_order_id)
        market_status = await broker.get_order_status(market_order_id)
        assert isinstance(limit_status, dict) and limit_status.get("order_id") == limit_order_id
        assert isinstance(market_status, dict) and market_status.get("order_id") == market_order_id

        await asyncio.sleep(1.0)
        orders_snapshot = broker.sync_orders()
        assert isinstance(orders_snapshot, list)

        # 市价单应能返回价格或状态字段，验证最基本的回报
        assert market_status.get("status") is not None or market_status.get("price") is not None

        cancelled = await broker.cancel_order(limit_order_id)
        assert isinstance(cancelled, bool)
    finally:
        broker.disconnect()
