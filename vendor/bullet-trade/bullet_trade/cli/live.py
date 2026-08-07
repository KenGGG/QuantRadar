"""
实盘命令入口

调用 LiveEngine 承载真实交易逻辑。
"""

import os
from pathlib import Path
from typing import Dict, Optional

from bullet_trade.core.live_engine import LiveEngine


def run_live(args, live_config_override: Optional[Dict[str, str]] = None):
    """加载策略并启动 LiveEngine。"""
    strategy_file = Path(args.strategy_file).expanduser().resolve()
    overrides: Dict[str, str] = dict(live_config_override or {})

    runtime_dir_arg = getattr(args, "runtime_dir", None)
    if runtime_dir_arg:
        resolved_runtime = str(Path(runtime_dir_arg).expanduser().resolve())
        overrides["runtime_dir"] = resolved_runtime
        os.environ["RUNTIME_DIR"] = resolved_runtime

    engine = LiveEngine(
        strategy_file=strategy_file,
        broker_name=getattr(args, "broker", None),
        live_config=overrides or None,
    )
    return engine.run()
