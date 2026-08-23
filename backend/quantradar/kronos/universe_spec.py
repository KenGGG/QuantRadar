"""可配置信号宇宙（universe）规格。

Kronos 信号研究只需要 OHLC(+volume/amount) 与交易日期，并不依赖某个指数
的 Point-in-Time 成分快照。本模块把「信号宇宙」抽象为可配置项：

- ``ALL_A_LIQUID``（默认）：由持续更新的 ``final_a_stock_eod_price`` 直接枚举，
  完全 Point-in-Time、不查成分表、不要求任何 PIT 快照。Kronos 研究默认走这里。
- ``CSI300_PIT`` / ``CSI500_PIT`` / ``CSI1000_PIT``：沿用旧行为，基于对应指数
  的 ``ts_index_weight`` PIT 快照。该路径在缺少快照时仍会 ``raise``（对该宇宙正确）。

设计原则：能力可用 ≠ 数据完美。一个指数 PIT 能力缺失，不应阻塞所有研究。
"""
from __future__ import annotations

import datetime as dt
from enum import Enum
from typing import Any

from .data_audit.universe import last_trading_day_per_week


class Universe(str, Enum):
    """信号候选宇宙。值为对外稳定字符串，可被 CLI / JSON 直接消费。"""

    ALL_A_LIQUID = "all_a_liquid"
    CSI300_PIT = "csi300_pit"
    CSI500_PIT = "csi500_pit"
    CSI1000_PIT = "csi1000_pit"


# 指数成分快照表 ts_index_weight 使用的代码（数据库侧）。
INDEX_CODE = {
    Universe.CSI300_PIT: "000300.SH",
    Universe.CSI500_PIT: "000905.SH",
    Universe.CSI1000_PIT: "000852.SH",
}

# JoinQuant 侧指数代码（provider.get_index_stocks 使用）。
JQ_INDEX_CODE = {
    Universe.CSI300_PIT: "000300.XSHG",
    Universe.CSI500_PIT: "000905.XSHG",
    Universe.CSI1000_PIT: "000852.XSHG",
}

DEFAULT_UNIVERSE = Universe.ALL_A_LIQUID

# 仅纳入沪/深 A 股（排除 B 股、北交所 BJ*、指数代码 SH000xxx/SZ399xxx 等）。
# 与 Kronos 目标市场一致；final_a_stock_eod_price 同时含指数与北交所行情，必须显式过滤。
_A_SHARE_INTERNAL = (
    r"^(SH(60[0-9]|688|689)[0-9]{3}|SZ(00[0-9]|30[0-9])[0-9]{3})$"
)


def _date(value: dt.date | str | dt.datetime) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(value)


def list_signal_dates(
    provider,
    *,
    start: dt.date | str,
    end: dt.date | str,
    universe: Universe = DEFAULT_UNIVERSE,
) -> list[dt.date]:
    """返回 [start, end] 内可用的周度信号日（每周最后一个交易日）。

    - ``ALL_A_LIQUID``：直接取交易日历 ``ts_trade_day_calendar``，不依赖任何
      指数成分快照。
    - ``CSI*_PIT``：取该指数在 ``ts_index_weight`` 中有 PIT 快照的交易日。
    """
    start_s = _date(start)
    end_s = _date(end)
    if universe is Universe.ALL_A_LIQUID:
        latest = latest_price_date(provider.connection)
        if latest is None:
            return []
        end_s = min(end_s, latest)
        if start_s > end_s:
            return []
        rows = provider.connection.query(
            "SELECT date FROM ts_trade_day_calendar WHERE is_open = 1 "
            "AND date BETWEEN %s AND %s ORDER BY date",
            (start_s.isoformat(), end_s.isoformat()),
        )
        days = [row["date"] for row in rows if isinstance(row.get("date"), dt.date)]
        return last_trading_day_per_week(days)

    index_code = INDEX_CODE[universe]
    rows = provider.connection.query(
        "SELECT DISTINCT trade_date FROM ts_index_weight "
        "WHERE index_code = %s AND trade_date BETWEEN %s AND %s "
        "ORDER BY trade_date",
        (index_code, start_s.isoformat(), end_s.isoformat()),
    )
    return [
        value
        for row in rows
        if isinstance((value := row.get("trade_date")), dt.date)
    ]


def all_a_liquid_symbols(connection, as_of: dt.date) -> list[str]:
    """在 as_of 当日有有效行情的沪/深 A 股（内部代码）。

    完全 Point-in-Time：上市/存续由价格历史本身推导，无需证券主数据。
    已显式排除北交所（BJ*）与指数代码（SH000xxx / SZ399xxx 等）。
    """
    rows = connection.query(
        "SELECT DISTINCT symbol FROM final_a_stock_eod_price "
        "WHERE tradedate = %s AND symbol REGEXP %s",
        (as_of.isoformat(), _A_SHARE_INTERNAL),
    )
    return sorted(row["symbol"] for row in rows if row.get("symbol"))


def listed_trade_days(connection, symbol: str, as_of: dt.date) -> int:
    """截至 as_of 该标的在 ``final_a_stock_eod_price`` 中的不同交易日计数。

    PIT 正确：仅统计 <= as_of 的成交日，据此推导上市交易天数。
    """
    row = connection.query_one(
        "SELECT COUNT(DISTINCT tradedate) AS n FROM final_a_stock_eod_price "
        "WHERE symbol = %s AND tradedate <= %s",
        (symbol, as_of.isoformat()),
    ) or {}
    return int((row or {}).get("n") or 0)


def latest_price_date(connection) -> dt.date | None:
    """``final_a_stock_eod_price`` 的最大成交日，作为 all_a_liquid 的实时信号日。"""
    row = connection.query_one(
        "SELECT MAX(tradedate) AS max_date FROM final_a_stock_eod_price"
    ) or {}
    value = row.get("max_date") if row else None
    return value if isinstance(value, dt.date) else None


def parse_universe(value: str) -> Universe:
    """将 CLI 字符串解析为 Universe；非法值抛 ValueError。"""
    try:
        return Universe(value)
    except ValueError as exc:
        valid = ", ".join(member.value for member in Universe)
        raise ValueError(f"unknown universe '{value}'; choices: {valid}") from exc
