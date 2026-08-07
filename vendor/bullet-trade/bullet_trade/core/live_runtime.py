"""
Live 运行态管理

能力：
- 初始化/加载运行目录并恢复 g
- 周期性持久化 g
- 记录异步调度器游标与 Tick 订阅状态，重启后恢复
"""

from __future__ import annotations

import atexit
import json
import os
import pickle
import threading
import time
from datetime import datetime
from typing import Any, Dict, Optional, Sequence, Set, Tuple

from .globals import g


_runtime_dir: Optional[str] = None
_autosave_thread: Optional[threading.Thread] = None
_stop_flag = threading.Event()
_state_cache: Optional[Dict[str, Any]] = None
_state_lock = threading.Lock()
_restored_from_disk = False


def _g_path() -> str:
    assert _runtime_dir is not None
    return os.path.join(_runtime_dir, 'g.pkl')


def _state_path() -> str:
    assert _runtime_dir is not None
    return os.path.join(_runtime_dir, 'live_state.json')


def _load_state() -> Dict[str, Any]:
    global _state_cache
    if _runtime_dir is None:
        return {}
    with _state_lock:
        if _state_cache is not None:
            return _state_cache
        path = _state_path()
        try:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    _state_cache = json.load(f)
            else:
                _state_cache = {}
        except Exception:
            _state_cache = {}
        return _state_cache


def _write_state(state: Dict[str, Any]) -> None:
    if _runtime_dir is None:
        return
    with _state_lock:
        tmp = _state_path() + '.tmp'
        os.makedirs(os.path.dirname(tmp), exist_ok=True)
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)
            os.replace(tmp, _state_path())
            global _state_cache
            _state_cache = dict(state)
        except Exception:
            pass


def init_live_runtime(runtime_dir: str) -> None:
    """
    初始化 live 运行态：创建目录并尝试加载 g，同时准备扩展状态。
    """
    global _runtime_dir, _restored_from_disk
    _runtime_dir = os.path.abspath(os.path.expanduser(runtime_dir))
    os.makedirs(_runtime_dir, exist_ok=True)
    # 重置状态缓存
    global _state_cache
    _state_cache = None
    _restored_from_disk = False
    # 加载 g
    try:
        path = _g_path()
        if os.path.exists(path):
            with open(path, 'rb') as f:
                data = pickle.load(f)
            if isinstance(data, dict):
                # 仅替换内部数据字典
                g._data = data  # type: ignore[attr-defined]
                _restored_from_disk = True
    except Exception:
        # 读取失败不阻断
        pass


def save_g() -> None:
    """
    立即保存 g 到 RUNTIME_DIR/g.pkl。
    """
    if _runtime_dir is None:
        return
    try:
        tmp = _g_path() + '.tmp'
        with open(tmp, 'wb') as f:
            pickle.dump(getattr(g, '_data', {}), f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, _g_path())
    except Exception:
        pass


def _autosave_worker(interval_sec: int) -> None:
    while not _stop_flag.is_set():
        time.sleep(max(1, interval_sec))
        try:
            save_g()
        except Exception:
            continue


def start_g_autosave(interval_sec: int = 60) -> None:
    """
    启动后台线程周期性保存 g。
    """
    global _autosave_thread
    _stop_flag.clear()
    if _autosave_thread and _autosave_thread.is_alive():
        return
    _autosave_thread = threading.Thread(target=_autosave_worker, args=(interval_sec,), daemon=True)
    _autosave_thread.start()
    atexit.register(save_g)


def stop_g_autosave() -> None:
    _stop_flag.set()
    try:
        if _autosave_thread and _autosave_thread.is_alive():
            _autosave_thread.join(timeout=1)
    except Exception:
        pass


def load_scheduler_cursor() -> Optional[datetime]:
    """
    读取最近一次调度游标（用于重启恢复）。
    """
    state = _load_state()
    cursor = (state.get('scheduler') or {}).get('last_cursor')
    if not cursor:
        return None
    try:
        return datetime.fromisoformat(cursor)
    except Exception:
        return None


def persist_scheduler_cursor(dt: datetime) -> None:
    """
    保存调度游标。
    """
    state = _load_state()
    scheduler = dict(state.get('scheduler') or {})
    scheduler['last_cursor'] = dt.isoformat()
    state['scheduler'] = scheduler
    _write_state(state)


def load_subscription_state() -> Tuple[Set[str], Set[str]]:
    """
    返回上次记录的 tick 订阅（symbol & market）。
    """
    state = _load_state()
    record = state.get('subscriptions') or {}
    symbols = set(record.get('symbols') or [])
    markets = set(record.get('markets') or [])
    return symbols, markets


def persist_subscription_state(symbols: Sequence[str], markets: Sequence[str]) -> None:
    """
    保存 tick 订阅状态，便于重启恢复。
    """
    state = _load_state()
    state['subscriptions'] = {
        'symbols': sorted({str(s) for s in symbols}),
        'markets': sorted({str(m) for m in markets}),
    }
    _write_state(state)


def runtime_restored() -> bool:
    return _restored_from_disk


def load_strategy_metadata() -> Dict[str, Any]:
    state = _load_state()
    return dict(state.get('strategy') or {})


def persist_strategy_metadata(metadata: Dict[str, Any]) -> None:
    state = _load_state()
    state['strategy'] = metadata
    _write_state(state)
