from __future__ import annotations

from typing import Dict

from .base import AdapterBuilder, AdapterBundle

REGISTRY: Dict[str, AdapterBuilder] = {}


def register_adapter(server_type: str, builder: AdapterBuilder) -> None:
    REGISTRY[server_type] = builder


def get_adapter(server_type: str) -> AdapterBuilder:
    if server_type not in REGISTRY:
        raise KeyError(f"未注册的 server-type: {server_type}")
    return REGISTRY[server_type]


__all__ = ["register_adapter", "get_adapter", "AdapterBundle"]
