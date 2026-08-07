"""
针对 dividend_buy_and_hold 策略的端到端验证，聚焦于：

1. 银华日利与中国平安的分红是否按年度完整入账。
2. 首日建仓价格是否与真实行情一致（use_real_price 模式）。
3. 前复权收益与实际回测收益的一致性（扣除个税差异）。
"""
from __future__ import annotations

import importlib.util
from dataclasses import asdict
from datetime import date as Date
from datetime import datetime, timedelta, time as Time
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd
import pytest

from bullet_trade.core.engine import BacktestEngine
from bullet_trade.core.settings import get_settings
from bullet_trade.data.api import get_data_provider, set_data_provider


pytestmark = [pytest.mark.requires_network, pytest.mark.requires_jqdata]

STRATEGY_FILE = Path(__file__).with_name("dividend_buy_and_hold.py")
START_DATE = "2015-01-01"
END_DATE = "2016-01-31"
INITIAL_CASH = 1_000_000
SILVER_FUND = "511880.XSHG"
PINGAN_STOCK = "601318.XSHG"
FUND_TYPES = {"fund", "etf", "lof", "fja", "fjb"}


def _load_strategy_module():
    spec = importlib.util.spec_from_file_location(
        "strategy_dividend_buy_and_hold", STRATEGY_FILE
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _simulate_dividends(
    events: Iterable[Dict[str, object]],
    initial_shares: int,
    hold_start: Date,
) -> Tuple[pd.DataFrame, int]:
    """根据数据源事件模拟净现金流和持股数量演变。"""
    rows: List[Dict[str, object]] = []
    shares = int(initial_shares)
    for raw in sorted(events, key=lambda ev: pd.to_datetime(ev.get("date"))):
        event_date = pd.to_datetime(raw.get("date")).date()
        if event_date <= hold_start:
            continue

        shares_before = int(shares)
        scale = float(raw.get("scale_factor") or 1.0)
        per_base = int(raw.get("per_base") or 10)
        bonus_pre_tax = float(raw.get("bonus_pre_tax") or 0.0)
        sec_type = str(raw.get("security_type") or "stock").lower()

        if abs(scale - 1.0) > 1e-9:
            shares = int(round(shares * scale))

        if bonus_pre_tax <= 0:
            continue

        taxable = sec_type not in FUND_TYPES
        net_bonus = bonus_pre_tax * (0.8 if taxable else 1.0)
        shares_for_dividend = shares_before if abs(scale - 1.0) > 1e-9 else shares
        gross_cash = shares_for_dividend / per_base * bonus_pre_tax
        net_cash = shares_for_dividend / per_base * net_bonus

        rows.append(
            {
                "date": pd.to_datetime(event_date),
                "shares": shares_for_dividend,
                "shares_after": shares,
                "per_base": per_base,
                "bonus_pre_tax": bonus_pre_tax,
                "net_bonus": net_bonus,
                "gross_cash": gross_cash,
                "net_cash": net_cash,
                "withheld_tax": gross_cash - net_cash,
            }
        )

    columns = [
        "date",
        "shares",
        "shares_after",
        "per_base",
        "bonus_pre_tax",
        "net_bonus",
        "gross_cash",
        "net_cash",
        "withheld_tax",
    ]
    df = pd.DataFrame(rows, columns=columns)
    if not df.empty:
        df["year"] = df["date"].dt.year
    else:
        df["year"] = pd.Series(dtype=int)
    return df, shares


def _extract_price(
    df: pd.DataFrame,
    code: str,
    column: str = "close",
    row: str = "last",
) -> float:
    """提取指定列的首/末价格，兼容多层列结构。"""
    if df is None or df.empty:
        raise AssertionError(f"行情数据为空，无法提取 {code} 的 {column}")

    if row not in {"first", "last"}:
        raise ValueError("row 参数仅支持 'first' 或 'last'")

    target = df.iloc[0] if row == "first" else df.iloc[-1]
    value = None
    if column in df.columns:
        value = target[column]
    elif code in df.columns:
        value = target[code]
    elif (column, code) in df.columns:
        value = target[(column, code)]

    if value is None or pd.isna(value):
        raise AssertionError(f"无法从行情数据中提取 {code} 的 {column}")
    return float(value)


def _trade_map(trades: Iterable) -> Dict[str, Dict[str, float]]:
    """将 Trade 列表转为按标的索引的汇总信息。"""
    enriched: Dict[str, Dict[str, float]] = {}
    for trade in trades:
        info = asdict(trade)
        security = info["security"]
        amount = float(info["amount"])
        price = float(info["price"])
        commission = float(info.get("commission", 0.0) or 0.0)
        tax = float(info.get("tax", 0.0) or 0.0)
        enriched[security] = {
            "amount": amount,
            "price": price,
            "commission": commission,
            "tax": tax,
            "datetime": info["time"],
        }
    return enriched


def _expected_trade_price(engine: BacktestEngine, code: str, price: float, *, is_buy: bool) -> float:
    """套用引擎默认/自定义滑点与 tick 规则，复现真实成交价。"""
    settings = get_settings()
    if settings.slippage:
        adjusted = settings.slippage.calculate_slippage(price, is_buy)
    else:
        adjusted = engine._calc_trade_price_with_default_slippage(price, is_buy, code)
    return engine._round_to_tick(adjusted, code, is_buy=is_buy)


def test_dividend_buy_and_hold_end_to_end():
    """验证分红入账、首次成交价格以及前复权收益一致性。"""
    set_data_provider("jqdata")
    provider = get_data_provider()

    strategy_module = _load_strategy_module()
    engine = BacktestEngine(
        initialize=strategy_module.initialize,
        handle_data=getattr(strategy_module, "handle_data", None),
        before_trading_start=getattr(strategy_module, "before_trading_start", None),
        after_trading_end=getattr(strategy_module, "after_trading_end", None),
        process_initialize=getattr(strategy_module, "process_initialize", None),
    )

    results = engine.run(
        start_date=START_DATE,
        end_date=END_DATE,
        capital_base=INITIAL_CASH,
        frequency="daily",
        benchmark="000300.XSHG",
    )

    daily_df: pd.DataFrame = results["daily_records"]
    trades = results["trades"]
    events = results["events"]
    positions_df: pd.DataFrame = results["daily_positions"]

    assert not daily_df.empty, "回测每日数据为空"
    assert trades, "策略未产生任何交易"

    trade_info = _trade_map(trades)
    provider_events_map: Dict[str, List[Dict[str, object]]] = {}
    expected_df_map: Dict[str, pd.DataFrame] = {}
    final_share_map: Dict[str, int] = {}
    filtered_event_total = 0
    for code in (SILVER_FUND, PINGAN_STOCK):
        provider_events = provider.get_split_dividend(
            code, start_date=START_DATE, end_date=END_DATE
        )
        provider_events_map[code] = provider_events
        initial_amount = int(trade_info[code]["amount"])
        trade_date = trade_info[code]["datetime"].date()
        expected_df, final_shares = _simulate_dividends(
            provider_events, initial_amount, trade_date
        )
        expected_df_map[code] = expected_df
        final_share_map[code] = final_shares
        filtered_event_total += len(expected_df)

    # --- Check 3: 首日成交价格使用真实价格 ---
    morning_window_end = Time(9, 31)
    market_close_time = Time(15, 0)

    for code in (SILVER_FUND, PINGAN_STOCK):
        trade = trade_info[code]
        trade_dt: datetime = trade["datetime"]
        trade_time = trade_dt.time()

        raw_price: float | None = None
        if trade_time < morning_window_end:
            # 引擎在 09:31 前使用当日日线开盘价
            price_df = provider.get_price(
                security=code,
                end_date=trade_dt.date(),
                frequency="daily",
                fields=["open"],
                count=1,
                fq="pre",
                prefer_engine=True,
                pre_factor_ref_date=trade_dt.date(),
            )
            raw_price = _extract_price(price_df, code, column="open")
        elif trade_time >= market_close_time:
            # 收盘及之后场景（防御性分支），与引擎一致使用日线收盘价
            price_df = provider.get_price(
                security=code,
                end_date=trade_dt.date(),
                frequency="daily",
                fields=["close"],
                count=1,
                fq="pre",
                prefer_engine=True,
                pre_factor_ref_date=trade_dt.date(),
            )
            raw_price = _extract_price(price_df, code, column="close")
        else:
            minute_kwargs = dict(
                security=code,
                end_date=trade_dt,
                frequency="minute",
                fields=["close"],
                count=1,
                fq="pre",
                prefer_engine=True,
                pre_factor_ref_date=trade_dt.date(),
            )
            try:
                price_df = provider.get_price(**minute_kwargs)
                raw_price = _extract_price(price_df, code, column="close")
            except AssertionError:
                # 若直接拉末尾一分钟失败，则退回到 [trade_dt, trade_dt+1min) 区间
                price_df = provider.get_price(
                    security=code,
                    start_date=trade_dt,
                    end_date=trade_dt + timedelta(minutes=1),
                    frequency="minute",
                    fields=["close"],
                    fq="pre",
                    prefer_engine=True,
                    pre_factor_ref_date=trade_dt.date(),
                )
                raw_price = _extract_price(price_df, code, column="close")

        if raw_price is None:
            raise AssertionError(f"无法获取 {code} 在 {trade_dt} 的行情价格")
        reference_price = _expected_trade_price(engine, code, raw_price, is_buy=True)
        assert trade["price"] == pytest.approx(reference_price, rel=1e-4), (
            f"{code} 成交价 {trade['price']} 与行情价 {reference_price} 不符"
        )

    # --- Prepare事件聚合 ---
    event_df = pd.DataFrame(events)
    if event_df.empty:
        if filtered_event_total == 0:
            pytest.skip("聚宽分红接口返回空数据（可能离线或权限不足），跳过分红校验")
        pytest.fail("应收分红事件未记录")
    event_df["event_date"] = pd.to_datetime(event_df["event_date"]).dt.normalize()

    withheld_total = 0.0
    theoretical_final = float(daily_df["cash"].iloc[0])  # 初始剩余现金
    actual_dividend_counts: Dict[str, int] = {}
    expected_dividend_counts: Dict[str, int] = {}

    # --- Check 1 & 2: 分红逐年匹配 ---
    for code in (SILVER_FUND, PINGAN_STOCK):
        expected_df = expected_df_map[code]
        final_shares = final_share_map[code]

        actual_df = (
            event_df[(event_df["code"] == code) & (event_df["event_type"] == "现金分红")]
            .copy()
            .rename(columns={"event_date": "date"})
        )
        actual_df["year"] = actual_df["date"].dt.year

        expected_years = set(expected_df["year"].unique())
        actual_years = set(actual_df["year"].unique())
        assert actual_years == expected_years, (
            f"{code} 分红年份不匹配，实际 {sorted(actual_years)}, 预期 {sorted(expected_years)}"
        )

        if not expected_df.empty:
            aggregated_expected = expected_df.groupby("year")["net_cash"].sum()
            aggregated_actual = actual_df.groupby("year")["cash_in"].sum()
            aggregated_expected = aggregated_expected.reindex(sorted(expected_years))
            aggregated_actual = aggregated_actual.reindex(sorted(expected_years))
            assert (aggregated_actual.values == pytest.approx(aggregated_expected.values, rel=1e-3)), (
                f"{code} 年度分红金额与数据源不一致"
            )

            withheld_total += float(expected_df["withheld_tax"].sum())

        expected_dividend_counts[code] = int(len(expected_df))
        actual_dividend_counts[code] = int(len(actual_df))

        # 校验最终持仓数量一致
        final_position = (
            positions_df[positions_df["code"] == code]
            .sort_values("date")
            .iloc[-1]["amount"]
        )
        assert int(final_position) == final_shares, f"{code} 最终持仓数量与模拟不一致"

        net_invest = trade_info[code]["amount"] * trade_info[code]["price"]
        price_series = provider.get_price(
            security=code,
            start_date=START_DATE,
            end_date=END_DATE,
            frequency="daily",
            fields=["close"],
            fq="pre",
            prefer_engine=True,
            pre_factor_ref_date=pd.to_datetime(END_DATE).date(),
        )
        price_series = price_series.dropna()
        start_price = _extract_price(price_series, code, row="first")
        end_price = _extract_price(price_series, code)
        ratio = end_price / start_price
        theoretical_final += net_invest * ratio

    final_total = float(daily_df["total_value"].iloc[-1])
    final_cash = float(daily_df["cash"].iloc[-1])
    initial_leftover = float(daily_df["cash"].iloc[0])

    assert final_cash > initial_leftover, "分红后现金余额应增加"

    # --- Check 4: 前复权收益与实际收益基本一致（差异源于个税） ---
    adjusted_final = theoretical_final - withheld_total
    diff_amount = final_total - adjusted_final
    diff_percent = diff_amount / adjusted_final if adjusted_final else float("inf")
    message = (
        "实际收益与前复权收益（扣除税款）差异过大。\n"
        f"策略回测初始资金: {INITIAL_CASH:,.2f}，最终资金: {final_total:,.2f}。\n"
        f"前复权模拟初始资金: {INITIAL_CASH:,.2f}，最终资金: {adjusted_final:,.2f} "
        f"(累计预扣税 {withheld_total:,.2f})。\n"
        f"{SILVER_FUND} 分红次数: 实际 {actual_dividend_counts.get(SILVER_FUND, 0)}，"
        f"模拟 {expected_dividend_counts.get(SILVER_FUND, 0)}；"
        f"{PINGAN_STOCK} 分红次数: 实际 {actual_dividend_counts.get(PINGAN_STOCK, 0)}，"
        f"模拟 {expected_dividend_counts.get(PINGAN_STOCK, 0)}。\n"
        f"最终差异金额: {diff_amount:,.2f}，差异百分比: {diff_percent:.4%}。"
    )
    assert final_total == pytest.approx(adjusted_final, rel=1e-2, abs=200.0), message
