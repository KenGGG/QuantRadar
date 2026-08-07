"""真实回测执行（复用 BulletTrade，禁止重实现撮合/账户/订单/成交/调度）。

把「执行一次真实回测并产出 Snapshot」的逻辑集中在此，供：
  - /api/backtest（内置 Buy&Hold）
  - /api/backtest/strategy（用户源码）
  - BacktestWorker（异步）
共用。所有价格/撮合/账户均来自 BulletTrade + InvestmentDataProvider。
"""

from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, Optional, Tuple

from quantradar.snapshot import build_snapshot


def run_backtest(
    *,
    code: Optional[str] = None,
    security: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    initial_cash: float = 500000.0,
    frequency: str = "day",
    amount: int = 100,
    extras: Optional[Dict[str, Any]] = None,
) -> Tuple[Any, Dict[str, Any]]:
    """运行一次真实回测，返回 (engine, snapshot)。

    - code 非空：用户策略源码（JoinQuant 兼容），写入临时 .py 经 BacktestEngine(strategy_file=) 执行。
    - code 为空：内置 Buy&Hold（对 security 建仓并持有）。
    """
    from bullet_trade.core.engine import BacktestEngine

    from quantradar.bootstrap import bootstrap_investment_data

    bootstrap_investment_data(set_active=True, overwrite=True)

    if code:
        tmp = tempfile.NamedTemporaryFile(
            "w", suffix=".py", delete=False, prefix="qr_strategy_", encoding="utf-8"
        )
        tmp.write(code)
        tmp.close()
        try:
            engine = BacktestEngine(
                strategy_file=tmp.name,
                start_date=start_date,
                end_date=end_date,
                frequency=frequency,
                initial_cash=initial_cash,
            )
            engine.run()
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
        snapshot = build_snapshot(engine, extras=extras, strategy_source=code)
        return engine, snapshot

    # 内置 Buy&Hold
    sec = security or "600519.XSHG"

    def _init(context):  # noqa: ANN001
        context._qr_security = sec
        context._qr_amount = amount

    def _handle(context, data):  # noqa: ANN001
        if not context.portfolio.positions:
            order_target(context._qr_security, context._qr_amount)

    engine = BacktestEngine(
        initialize=_init,
        handle_data=_handle,
        start_date=start_date,
        end_date=end_date,
        frequency=frequency,
        initial_cash=initial_cash,
    )
    engine.run()
    snapshot = build_snapshot(engine, extras=extras, strategy_source=None)
    return engine, snapshot
