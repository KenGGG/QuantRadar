"""
策略消息通知工具

提供聚宽风格的 send_msg API，并在配置 MESSAGE_KEY 时
通过企业微信机器人 webhook 发送消息。
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

try:
    import requests
except ImportError:  # pragma: no cover - requests 是必装依赖，防御性降级
    requests = None  # type: ignore

from .globals import log
from ..utils.env_loader import get_env, load_env

_LOGGER = logging.getLogger(__name__)
_WEBHOOK_TEMPLATE = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}"
_DEFAULT_TIMEOUT = 5
_message_handler: Optional[Callable[[str], None]] = None
_ENV_LOADED = False


def set_message_handler(handler: Optional[Callable[[str], None]]) -> None:
    """注册自定义消息处理函数，传入 None 可清除。"""
    global _message_handler
    _message_handler = handler


def send_msg(message: str) -> None:
    """
    发送策略通知。

    - 始终记录 `[策略消息]` 日志。
    - 存在自定义 handler 时优先调用，异常不会向外抛出。
    - 配置 MESSAGE_KEY 时，会尝试调用企业微信 webhook。
    """
    text = str(message)
    log.info(f"[策略消息] {text}")

    if _message_handler:
        try:
            _message_handler(text)
        except Exception as exc:  # pragma: no cover - 防御性保护
            _LOGGER.exception("自定义消息处理失败: %s", exc)

    global _ENV_LOADED
    if not _ENV_LOADED:
        try:
            load_env()
        except Exception as exc:  # pragma: no cover - 加载失败仅记录
            _LOGGER.debug("加载 .env 失败: %s", exc)
        _ENV_LOADED = True

    key = get_env("MESSAGE_KEY") or get_env("WECHAT_MESSAGE_KEY")
    if not key:
        return

    if requests is None:
        _LOGGER.error("requests 未安装，无法发送企业微信消息")
        return

    url = _WEBHOOK_TEMPLATE.format(key=key)
    payload = {
        "msgtype": "text",
        "text": {"content": text, "mentioned_list": ["@all"]},
    }

    try:
        response = requests.post(url, json=payload, timeout=_DEFAULT_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and data.get("errcode") != 0:
            _LOGGER.error("企业微信返回错误: %s", data)
    except Exception as exc:  # pragma: no cover - 网络异常路径不固定
        _LOGGER.exception("发送企业微信消息失败: %s", exc)


__all__ = ["send_msg", "set_message_handler"]
