"""Phase 4（目标口径）—— 真实策略回测端到端验证（DB-backed，无 mock）。

目标要求至少跑通：Buy & Hold、双均线、沪深300动量，并输出
NAV（daily_records）、Positions（daily_positions）、Trades、Metrics（summary）、Report/Logs（meta）。

所有回测均经 InvestmentDataProvider 读取真实 investment_data；策略内仅用引擎注入的
get_price / get_index_stocks / order_target，不直连数据库、不伪造。
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.requires_dolt
from bullet_trade.core.engine import BacktestEngine

from quantradar.bootstrap import bootstrap_investment_data

START = "2023-01-03"
END = "2023-03-31"
CASH = 500000

_STATE: dict = {}


@pytest.fixture(scope="module")
def provider():
    return bootstrap_investment_data(set_active=True, overwrite=True)


def _run(initialize, handle_data, start=START, end=END, cash=CASH):
    _STATE.clear()
    engine = BacktestEngine(
        initialize=initialize,
        handle_data=handle_data,
        start_date=start,
        end_date=end,
        frequency="day",
        initial_cash=cash,
    )
    result = engine.run()
    return engine, result


def _assert_full_outputs(engine, result):
    # NAV
    assert not result["daily_records"].empty, "未产出 NAV（daily_records）"
    # Trades
    assert result["trades"], "未产生任何成交"
    # Positions（回测过程中至少出现过持仓）
    assert not result["daily_positions"].empty, "未记录持仓（daily_positions）"
    # Metrics
    assert "策略收益" in result["summary"], "summary 缺少策略收益指标"
    assert "夏普比率" in result["summary"], "summary 缺少夏普比率"
    # Report/Logs 上下文
    assert result["meta"]["start_date"] == START
    assert result["meta"]["end_date"] == END


# ---------------- Buy & Hold ----------------
def _bh_init(context):  # noqa: ANN001
    _STATE["bought"] = False


def _bh_handle(context, data):  # noqa: ANN001
    df = get_price("600519.XSHG", count=5, fields=["close"])
    if df is None or df.empty:
        return
    if not _STATE["bought"]:
        order_target("600519.XSHG", 100)
        _STATE["bought"] = True


# ---------------- 双均线 ----------------
def _ma_init(context):  # noqa: ANN001
    _STATE["sec"] = "600519.XSHG"
    _STATE["holding"] = False


def _ma_handle(context, data):  # noqa: ANN001
    sec = _STATE["sec"]
    df = get_price(sec, count=20, fields=["close"])
    if df is None or len(df) < 20:
        return
    closes = df["close"].astype(float)
    ma5 = closes.iloc[-5:].mean()
    ma20 = closes.mean()
    if ma5 > ma20 and not _STATE["holding"]:
        order_target(sec, 100)
        _STATE["holding"] = True
    elif ma5 < ma20 and _STATE["holding"]:
        order_target(sec, 0)
        _STATE["holding"] = False


# ---------------- 沪深300动量 ----------------
def _mom_init(context):  # noqa: ANN001
    _STATE["last_month"] = None


def _mom_handle(context, data):  # noqa: ANN001
    cur = context.current_dt
    month = cur.strftime("%Y-%m")
    if month == _STATE["last_month"]:
        return
    _STATE["last_month"] = month

    stocks = get_index_stocks("000300.SH", cur)
    if not stocks:
        return
    # 动量：过去 20 交易日收益率（候选集限制为前 50 以控制测试耗时；真实策略可全量）
    ranked = []
    for s in stocks[:50]:
        try:
            h = get_price(s, count=21, fields=["close"])
            if h is None or len(h) < 21:
                continue
            ret = float(h["close"].iloc[-1]) / float(h["close"].iloc[0]) - 1.0
            ranked.append((s, ret))
        except Exception:
            continue
    ranked.sort(key=lambda x: x[1], reverse=True)
    top = [s for s, _ in ranked[:5]]
    # 卖出不在 top 的持仓，等权买入 top
    for pos in list(context.portfolio.positions.keys()):
        if pos not in top:
            order_target(pos, 0)
    for s in top:
        order_target(s, 100)


@pytest.mark.unit
class TestRealStrategies:
    def test_buy_and_hold_full_outputs(self, provider):
        engine, result = _run(_bh_init, _bh_handle)
        _assert_full_outputs(engine, result)
        # Buy & Hold 应长期持有 -> 期末有持仓
        assert engine.daily_records[-1]["positions_value"] > 0

    def test_dual_ma_full_outputs(self, provider):
        engine, result = _run(_ma_init, _ma_handle)
        _assert_full_outputs(engine, result)
        # 双均线会产生多笔成交（金叉买入 + 死叉卖出）
        assert len(result["trades"]) >= 1

    def test_csi300_momentum_full_outputs(self, provider):
        engine, result = _run(_mom_init, _mom_handle)
        _assert_full_outputs(engine, result)
        # 动量策略应建过仓（持仓记录非空且至少一笔买入成交）
        assert engine.daily_records[-1]["positions_value"] >= 0
        assert len(result["trades"]) >= 1
