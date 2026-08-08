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
import threading
from typing import Any, Dict, List, Optional, Tuple

from bullet_trade.core.settings import get_settings, set_option

from quantradar.snapshot import _to_native, build_snapshot

# 保护 bullet_trade 全局 use_real_price 设置在「设置 → 回测 → 还原」临界区内的线程安全。
# 单进程内回测本就基本串行；此锁避免 Worker 多线程并发提交时复权口径互相串扰。
_FQ_LOCK = threading.Lock()


def _serialize_trades(engine: Any) -> List[Dict[str, Any]]:
    """把引擎成交对象序列化为原生 JSON 可序列化 dict 列表。"""
    trades = getattr(engine, "trades", []) or []
    out = []
    for t in trades:
        out.append(
            {
                "security": getattr(t, "security", None),
                "action": getattr(t, "action", None) or ("BUY" if (getattr(t, "amount", 0) or 0) >= 0 else "SELL"),
                "amount": _to_native(getattr(t, "amount", None)),
                "price": _to_native(getattr(t, "price", None)),
                "value": _to_native(getattr(t, "value", None)),
                "commission": _to_native(getattr(t, "commission", None)),
                "time": _to_native(getattr(t, "time", None)),
            }
        )
    return out


def _serialize_positions(engine: Any) -> List[Dict[str, Any]]:
    """把引擎持仓序列化为原生 JSON 可序列化 dict 列表。"""
    port = getattr(getattr(engine, "context", None), "portfolio", None)
    positions = getattr(port, "positions", {}) or {}
    out = []
    for sec, p in positions.items():
        out.append(
            {
                "security": sec or getattr(p, "security", None),
                "amount": _to_native(getattr(p, "total_amount", None) or getattr(p, "amount", None)),
                "avg_cost": _to_native(getattr(p, "avg_cost", None)),
                "price": _to_native(getattr(p, "price", None)),
                "value": _to_native(getattr(p, "value", None)),
            }
        )
    return out


def _attach_details(snapshot: Dict[str, Any], engine: Any) -> Dict[str, Any]:
    """在审计快照上附加回测明细（daily_records/trades/positions），供 WebUI 画图与表格。

    审计字段（result_hash/metrics/environment 等）已在 build_snapshot 中计算，不受影响；
    明细仅做原生 JSON 化，不进入指纹计算。
    """
    snapshot = dict(snapshot)
    snapshot["daily_records"] = _to_native(getattr(engine, "daily_records", []) or [])
    snapshot["trades"] = _serialize_trades(engine)
    snapshot["positions"] = _serialize_positions(engine)
    return snapshot


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
    benchmark: Optional[str] = None,
    fq: str = "none",
) -> Tuple[Any, Dict[str, Any]]:
    """运行一次真实回测，返回 (engine, snapshot)。

    - code 非空：用户策略源码（JoinQuant 兼容），写入临时 .py 经 BacktestEngine(strategy_file=) 执行。
    - code 为空：内置 Buy&Hold（对 security 建仓并持有）。
    benchmark 仅作为审计/配置字段记录（不参与撮合，撮合由 BulletTrade 负责）。

    复权口径（fq）：
      - 'none'（默认）：真实现金流水，撮合用原始价，含除权除息跳变（适合真实现金归因）。
      - 'pre'/'qfq'/'post'/'hfq'：连续复权撮合（启用 bullet_trade use_real_price），净值连续、
        除权日无假跳变。注意 bullet_trade 撮合统一以「前复权(pre)」执行；后复权(hfq/post)与前
        复权(qfq/pre) 在同一回测窗口内收益率严格等价（仅净值绝对水平缩放常数因子），故与 Qlib
        训练所用的后复权(hfq)收益率一致——严谨研究型回测默认用连续复权口径。
    """
    from bullet_trade.core.engine import BacktestEngine

    from quantradar.bootstrap import bootstrap_investment_data

    _fq = (fq or "none").lower()
    if _fq not in ("none", "pre", "qfq", "post", "hfq"):
        raise ValueError(
            f"run_backtest: 不支持的复权方式 fq={fq!r}；"
            f"支持 none（真实现金流水，含除权跳变）/ pre / qfq / post / hfq（连续复权）"
        )
    # bullet_trade 撮合仅区分「原始价(none)」与「连续前复权(pre)」；后复权(hfq/post)与前复权
    # (qfq/pre) 在同一回测窗口内收益率严格等价（仅净值绝对水平缩放常数因子）。无论请求何种
    # 连续复权，撮合统一启用 use_real_price（pre），使账户净值连续、除权日无假跳变，与 Qlib
    # 训练所用的后复权(hfq)收益率一致（严谨研究型口径）。
    _use_real_price = _fq != "none"

    with _FQ_LOCK:
        _prev_real_price = get_settings().options.get("use_real_price", False)
        set_option("use_real_price", _use_real_price)
        try:
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
                snapshot = build_snapshot(
                    engine, extras=extras, strategy_source=code,
                    security=security, amount=amount, benchmark=benchmark, fq=_fq,
                )
                return engine, _attach_details(snapshot, engine)

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
            snapshot = build_snapshot(
                engine, extras=extras, strategy_source=None,
                security=sec, amount=amount, benchmark=benchmark, fq=_fq,
            )
            return engine, _attach_details(snapshot, engine)
        finally:
            set_option("use_real_price", _prev_real_price)
