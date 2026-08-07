"""
运行时辅助：持有当前引擎实例并提供即时撮合入口
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Optional

_current_engine: Optional[Any] = None


def set_current_engine(engine: object) -> None:
    """注册当前运行的引擎实例"""
    global _current_engine
    _current_engine = engine


def get_current_engine() -> Optional[object]:
    """获取当前引擎，如果不存在则返回 None"""
    return _current_engine


def process_orders_now() -> None:
    """
    立即处理订单队列。
    依赖当前引擎的 `_process_orders` 方法，若当前引擎不存在则静默返回。
    """
    engine = get_current_engine()
    if engine is None:
        return

    try:
        result = engine._process_orders(engine.context.current_dt)
        if inspect.isawaitable(result):
            loop = getattr(engine, "_loop", None)
            if loop and loop.is_running():
                fut = asyncio.run_coroutine_threadsafe(result, loop)
                fut.result()
            else:
                asyncio.run(result)
    except Exception:
        raise
