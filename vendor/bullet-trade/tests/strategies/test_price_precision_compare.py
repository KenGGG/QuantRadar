from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

from bullet_trade.core.engine import BacktestEngine
from bullet_trade.core.globals import g
from bullet_trade.utils.env_loader import load_env


pytestmark = [pytest.mark.requires_network, pytest.mark.requires_jqdata]

STRATEGY_FILE = Path(__file__).with_name("price_precision_compare.py")


def _load_strategy_module():
    spec = importlib.util.spec_from_file_location(
        "strategy_price_precision_compare", STRATEGY_FILE
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _require_jqdata():
    load_env()
    if not os.getenv("JQDATA_USERNAME") or not os.getenv("JQDATA_PASSWORD"):
        pytest.skip("缺少 JQDATA_USERNAME/JQDATA_PASSWORD，跳过精度对比用例")
    try:
        import jqdatasdk  # noqa: F401
    except Exception:
        pytest.skip("未安装 jqdatasdk，跳过精度对比用例")


def test_price_precision_compare():
    _require_jqdata()
    strategy = _load_strategy_module()
    engine = BacktestEngine(
        initialize=strategy.initialize,
        handle_data=getattr(strategy, "handle_data", None),
        before_trading_start=getattr(strategy, "before_trading_start", None),
        after_trading_end=getattr(strategy, "after_trading_end", None),
        process_initialize=getattr(strategy, "process_initialize", None),
    )

    engine.run(
        start_date="2024-06-03",
        end_date="2024-06-03",
        capital_base=100000,
        frequency="daily",
        benchmark="000300.XSHG",
    )

    results = getattr(g, "results", {}) or {}
    errors = results.get("errors") or []
    assert not errors, "策略执行失败:\n" + "\n".join(errors)

    minute_checks = results.get("minute_checks") or []
    assert minute_checks, "未获取到盘中分钟行情结果"
    for item in minute_checks:
        diff = float(item.get("diff", 1.0))
        assert diff <= 1e-6, f"{item.get('code')} 分钟价未对齐小数位: diff={diff}"

    pre_close = results.get("pre_close") or {}
    assert pre_close, "未获取到前复权价格结果"
    assert pre_close.get("rounded_close") == 5.09, (
        f"{pre_close.get('code')} 前复权价格不匹配: "
        f"{pre_close.get('rounded_close')}"
    )
