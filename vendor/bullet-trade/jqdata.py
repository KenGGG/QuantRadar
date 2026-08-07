"""
jqdata 兼容模块（项目根目录）

支持 `from jqdata import *` 直接导入 BulletTrade 的 API。
"""

import bullet_trade.compat.jqdata as _compat_jq
from bullet_trade.compat.jqdata import *  # noqa: F401,F403

try:
    __all__ = list(_compat_jq.__all__)  # type: ignore[attr-defined]
except AttributeError:
    __all__ = [name for name in globals().keys() if not name.startswith("_")]
