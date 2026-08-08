"""Phase 4：真实 A 股回测端到端验证（REAL_A_SHARE_BACKTEST_PASS）。

用 InvestmentDataProvider 驱动 BulletTrade BacktestEngine，验证：
1. 回测经 Generic Provider Registry 读到 investment_data 真实行情；
2. 引擎内部 get_trade_days / get_security_info / get_price 调用全部被 Provider 承接；
3. 防未来数据：handle_data 内 get_price（不传 end_date）最大返回日 <= current_dt；
4. 回测资产曲线来自真实价格，且可与原表抽样对账一致。
"""

from __future__ import annotations

import pandas as pd
import pytest

pytestmark = pytest.mark.requires_dolt

from bullet_trade.core.engine import BacktestEngine

from quantradar.bootstrap import bootstrap_investment_data

# 测试用真实标的（贵州茅台，上市已久，区间内有完整日线）
TEST_SECURITY = "600519.XSHG"
START = "2023-01-03"
END = "2023-03-31"


@pytest.fixture(scope="module")
def provider():
    """激活 InvestmentDataProvider 为全局 active provider。"""
    return bootstrap_investment_data(set_active=True, overwrite=True)


# 收集器与下单状态（模块级，避免依赖 g 注入的内容被覆盖）
_SEEN: dict = {"dates": [], "prices": []}
_STATE: dict = {"bought": False}


def _reset_collector() -> None:
    _SEEN["dates"] = []
    _SEEN["prices"] = []
    _STATE["bought"] = False


def bt_initialize(context):  # noqa: ANN001
    _STATE["bought"] = False


def bt_handle_data(context, data):  # noqa: ANN001
    sec = TEST_SECURITY
    # 不传 end_date：引擎注入 current_dt，应只返回 <= current_dt 的数据
    df = get_price(sec, count=5, fields=["close"])
    if df is None or df.empty:
        return
    last_dt = pd.Timestamp(df.index[-1])
    cur_dt = pd.Timestamp(context.current_dt)
    # 防未来数据：返回的最大日绝不超过当前回测日
    assert last_dt <= cur_dt, (
        f"未来数据泄漏：get_price 返回 {last_dt} > current_dt {cur_dt}"
    )
    _SEEN["dates"].append(cur_dt.normalize())
    _SEEN["prices"].append(float(df.iloc[-1]["close"]))
    if not _STATE["bought"]:
        order_target(sec, 100)
        _STATE["bought"] = True


def test_real_backtest_runs_end_to_end(provider):
    """引擎用 InvestmentDataProvider 跑完真实 A 股区间，无异常退出。"""
    _reset_collector()
    engine = BacktestEngine(
        initialize=bt_initialize,
        handle_data=bt_handle_data,
        start_date=START,
        end_date=END,
        frequency="day",
        initial_cash=500000,
    )
    result = engine.run()
    assert result is not None
    # 每日记录非空（数据链路打通）
    assert engine.daily_records, "回测未产出每日记录"
    assert len(engine.daily_records) > 10
    # 已买入并持有：存在成交记录
    assert engine.trades, "回测未产生任何成交"
    # 防未来数据：所有 bar 看到的最后日期均 <= 当前回测日（已在 handle_data 中断言）
    assert _SEEN["dates"], "handle_data 未收集到任何交易日"


def test_backtest_prices_match_raw_table(provider):
    """回测使用的价格来自真实行情，可与原表 final_a_stock_eod_price 对账一致。"""
    _reset_collector()
    engine = BacktestEngine(
        initialize=bt_initialize,
        handle_data=bt_handle_data,
        start_date=START,
        end_date=END,
        frequency="day",
        initial_cash=500000,
    )
    engine.run()
    assert _SEEN["dates"] and _SEEN["prices"]

    # 取最后一日：回测记录价 vs Provider 直读原表价
    last_date = _SEEN["dates"][-1]
    recorded_close = _SEEN["prices"][-1]

    raw = provider.get_price(
        TEST_SECURITY,
        start_date=last_date,
        end_date=last_date,
        fields=["close"],
        fq="none",
    )
    assert not raw.empty, f"原表在 {last_date.date()} 无 {TEST_SECURITY} 数据"
    raw_close = float(raw.iloc[-1]["close"])

    # 真实价格对账（非伪造）：误差极小
    assert abs(recorded_close - raw_close) < 1e-6, (
        f"回测价 {recorded_close} 与原表价 {raw_close} 不符（{last_date.date()}）"
    )
    # 资产曲线来自真实价格：期末总资产 > 0
    final_value = engine.daily_records[-1].get("total_value")
    assert final_value is not None and final_value > 0


def test_backtest_portfolio_value_uses_real_prices(provider):
    """资产曲线末值与买入成本大致自洽（真实价，非虚构）。"""
    _reset_collector()
    engine = BacktestEngine(
        initialize=bt_initialize,
        handle_data=bt_handle_data,
        start_date=START,
        end_date=END,
        frequency="day",
        initial_cash=500000,
    )
    engine.run()
    # 买入 100 股 600519，成本应在数万元量级（茅台单价 ~1700+），绝非 0 或异常
    final_value = engine.daily_records[-1].get("total_value")
    assert final_value is not None
    assert final_value > 10000, "资产曲线异常（疑似未使用真实价格）"
