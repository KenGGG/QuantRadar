"""T3 Qlib 测试共享工具：构建一次 qlib 数据目录供多模型/网格/walk-forward 测试复用。

为什么共享同一目录？
    qlib 每个进程只能 qlib.init 一次（recorder 位置全局单例）。若各测试函数各自
    build_qlib_data 到不同临时目录，跨函数调用会触发 loop._ensure_qlib_init 的
    provider_uri 重定向；而重定向会把 joblib_backend 重置回默认的 'multiprocessing'，
    导致 qlib 的 inst_calculator 在 loky 子进程里因缺少已注册的 C 而崩溃
    （AttributeError: No such 'registered'）。

    统一用同一目录后，同进程内永不重定向（与真实「单目录/会话」用法一致），规避该陷阱。
    该目录覆盖 2020-2022、>=20 标的，足以支撑 models/grid(2020-2021) 与 walk(2020-2022)。
"""

from __future__ import annotations

import tempfile
from typing import Optional

_SHARED_DIR: Optional[str] = None


def build_shared_qlib_dir() -> str:
    """构建（进程内仅一次）并返回共享 qlib 数据目录。"""
    global _SHARED_DIR
    if _SHARED_DIR is None:
        from quantradar.qml import build_qlib_data

        d = tempfile.mkdtemp(prefix="qr_t3_shared_")
        # 覆盖范围取 models/grid/walk 的并集，保证三套测试都用同一目录也不会越界。
        build_qlib_data(d, start="2020-01-01", end="2022-12-31", max_instruments=20)
        _SHARED_DIR = d
    return _SHARED_DIR
