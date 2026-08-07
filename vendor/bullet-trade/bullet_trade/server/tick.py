from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Dict, Iterable, Optional, Set

from bullet_trade.core.globals import log


class TickSubscriptionManager:
    """
    简单的轮询式 tick 分发器：为订阅过的标的定期拉取最新行情并推送给 session。
    """

    def __init__(self, data_adapter, interval: float = 1.0, max_subscriptions: int = 200) -> None:
        self.data_adapter = data_adapter
        self.interval = max(interval, 0.2)
        self.max_subscriptions = max_subscriptions
        self._session_symbols: Dict["ClientSession", Set[str]] = defaultdict(set)
        self._symbol_sessions: Dict[str, Set["ClientSession"]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None
        self._running = asyncio.Event()

    async def start(self) -> None:
        if self._task:
            return
        self._running.set()
        self._task = asyncio.create_task(self._loop(), name="tick-loop")

    async def stop(self) -> None:
        self._running.clear()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def subscribe(self, session: "ClientSession", symbols: Iterable[str]) -> Dict[str, int]:
        cleaned = {s.strip().upper() for s in symbols if s}
        if not cleaned:
            return {"count": len(self._session_symbols.get(session, set()))}
        async with self._lock:
            current = self._session_symbols.get(session, set())
            if len(current) + len(cleaned - current) > self.max_subscriptions:
                raise ValueError(f"订阅数量超过上限 {self.max_subscriptions}")
            for symbol in cleaned:
                self._symbol_sessions[symbol].add(session)
            current.update(cleaned)
            self._session_symbols[session] = current
        return {"count": len(current)}

    async def unsubscribe(self, session: "ClientSession", symbols: Optional[Iterable[str]] = None) -> Dict[str, int]:
        async with self._lock:
            current = self._session_symbols.get(session)
            if not current:
                return {"count": 0}
            if symbols is None:
                symbols = list(current)
            removed = 0
            for symbol in symbols:
                symbol = symbol.strip().upper()
                if symbol in current:
                    current.remove(symbol)
                    bucket = self._symbol_sessions.get(symbol)
                    if bucket and session in bucket:
                        bucket.remove(session)
                        if not bucket:
                            self._symbol_sessions.pop(symbol, None)
                    removed += 1
            if not current:
                self._session_symbols.pop(session, None)
            return {"count": len(current), "removed": removed}

    async def remove_session(self, session: "ClientSession") -> None:
        await self.unsubscribe(session, None)

    async def _loop(self) -> None:
        try:
            while self._running.is_set():
                await asyncio.sleep(self.interval)
                symbols = list(self._symbol_sessions.keys())
                if not symbols:
                    continue
                await self._poll(symbols)
        except asyncio.CancelledError:  # pragma: no cover - shutdown path
            pass
        except Exception as exc:  # pragma: no cover - log unexpected
            log.error(f"Tick 循环异常: {exc}")

    async def _poll(self, symbols: Iterable[str]) -> None:
        for symbol in symbols:
            sessions = list(self._symbol_sessions.get(symbol) or [])
            if not sessions:
                continue
            try:
                tick = await self.data_adapter.get_current_tick(symbol)
            except Exception as exc:
                log.warning(f"拉取 tick {symbol} 失败: {exc}")
                continue
            if not tick:
                continue
            payload = {"symbol": symbol, **tick}
            for sess in sessions:
                asyncio.create_task(sess.send_event("tick", payload))


# 用于静态类型提示，避免循环导入
class ClientSession:  # pragma: no cover - 类型提示
    async def send_event(self, event: str, payload: Dict) -> None: ...
