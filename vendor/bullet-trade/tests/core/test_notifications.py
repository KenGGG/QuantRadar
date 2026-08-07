import logging
import os
from types import SimpleNamespace

import pytest

from bullet_trade.core import notifications


def teardown_function():
    # 重置 handler，避免测试间串扰
    notifications.set_message_handler(None)
    notifications._ENV_LOADED = False


def test_send_msg_logs_and_handler(monkeypatch, caplog):
    monkeypatch.delenv("MESSAGE_KEY", raising=False)
    notifications._ENV_LOADED = False
    monkeypatch.setattr(notifications, "load_env", lambda: None)

    calls = []
    notifications.set_message_handler(lambda msg: calls.append(msg))

    caplog.set_level(logging.INFO, logger="jq_strategy")

    notifications.send_msg("测试消息")

    assert calls == ["测试消息"]
    assert any(
        "[策略消息] 测试消息" in record.getMessage() for record in caplog.records
    )


def test_send_msg_triggers_webhook(monkeypatch):
    monkeypatch.setenv("MESSAGE_KEY", "dummy-key")
    notifications._ENV_LOADED = False
    monkeypatch.setattr(notifications, "load_env", lambda: None)

    request_payload = {}

    def fake_post(url, json=None, timeout=None):
        request_payload["url"] = url
        request_payload["json"] = json
        request_payload["timeout"] = timeout
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"errcode": 0},
        )

    monkeypatch.setattr(notifications, "requests", SimpleNamespace(post=fake_post))

    notifications.send_msg("hello world")

    assert (
        request_payload["url"]
        == "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=dummy-key"
    )
    assert request_payload["json"]["text"]["content"] == "hello world"
    assert request_payload["timeout"] == 5


@pytest.mark.requires_network
def test_send_msg_wechat_live(monkeypatch):
    key = os.getenv("MESSAGE_KEY")
    if not key:
        pytest.skip("未配置 MESSAGE_KEY，跳过真实 webhook 测试")

    notifications._ENV_LOADED = False
    # 使用独立 handler 确保不会重复触发其它通道
    notifications.set_message_handler(None)
    notifications.send_msg("BulletTrade send_msg smoke test")
