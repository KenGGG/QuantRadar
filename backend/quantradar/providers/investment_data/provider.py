"""InvestmentDataProvider —— investment_data（Dolt 只读）的 BulletTrade DataProvider 实现。

Phase 2A 范围（仅基础能力与历史时点查询，禁止伪造 / 禁止写操作）：
    - 只读连接（connection.py）
    - 证券代码映射（symbols.py）
    - get_trade_days
    - get_all_securities（Point-in-Time）
    - get_security_info
    - get_index_stocks（Point-in-Time）
    - get_index_weights（Point-in-Time）
    - get_split_dividend / get_price：本阶段显式 NotImplementedError（分别在 Phase 5 / 2B）

数据正确性优先：所有历史查询按 date 截断到「当时可得」，避免未来函数与幸存者偏差。
缺数据（如证券 display_name）明确标记 PARTIAL/LIMIT，绝不默认填充正常值。
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any, Dict, List, Optional, Union

import pandas as pd
from bullet_trade.data.providers.base import DataProvider

from ...config import InvestmentDataConfig, load_investment_data_config
from .capabilities import CAPABILITIES
from .connection import (
    InvestmentDataConnection,
    InvestmentDataConnectionError,
)
from .symbols import (
    SymbolError,
    normalize_index_symbol,
    to_joinquant_symbol,
    to_ts_symbol,
)

# 交易日历统一采用 SSE（A 股沪市日历；investment_data 仅 SSE 行，已被审计为可接受）
_CALENDAR_EXCHANGE = "SSE"

# get_all_securities / get_security_info 输出的列（与 BulletTrade 内置 Provider 对齐）
_SECURITIES_COLUMNS = ["display_name", "name", "start_date", "end_date", "type"]


def _fmt_date(value: Optional[Union[str, datetime, pd.Timestamp]]) -> Optional[str]:
    """归一化为 'YYYY-MM-DD' 字符串；None 原样返回。"""
    if value is None:
        return None
    return pd.to_datetime(value).strftime("%Y-%m-%d")


def _as_datetime(date_value) -> datetime:
    """date -> 当日 00:00:00 的 naive datetime（与内置 get_trade_days 返回类型一致）。"""
    ts = pd.to_datetime(date_value)
    return datetime.combine(ts.date(), time(0, 0))


def _is_open(raw) -> bool:
    """ts_trade_day_calendar.is_open 为 binary(1)，可能以 bytes 返回；归一判断。"""
    if raw is None:
        return False
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="ignore")
    return str(raw).strip() in ("1", "1")


class InvestmentDataProvider(DataProvider):
    name = "investment_data"

    def __init__(self, config: Optional[InvestmentDataConfig] = None) -> None:
        self._config = config or load_investment_data_config()
        self._connection = InvestmentDataConnection(self._config)

    # -- 连接 / 认证 ------------------------------------------------------

    @property
    def connection(self) -> InvestmentDataConnection:
        return self._connection

    def auth(self, user=None, pwd=None, host=None, port=None) -> None:
        """provider 认证即连接探针；失败抛明确异常（set_data_provider 会吞掉，
        bootstrap 另有显式 check）。"""
        try:
            self._connection.check()
        except InvestmentDataConnectionError as exc:
            raise InvestmentDataConnectionError(
                f"InvestmentDataProvider 连接校验失败：{exc}"
            ) from exc

    def capabilities(self) -> Dict[str, Dict[str, str]]:
        return dict(CAPABILITIES)

    # -- get_trade_days ---------------------------------------------------

    def get_trade_days(
        self,
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None,
        count: Optional[int] = None,
    ) -> List[datetime]:
        start = _fmt_date(start_date)
        end = _fmt_date(end_date)

        sql = "SELECT date, is_open FROM ts_trade_day_calendar WHERE exchange = %s"
        args: List[Any] = [_CALENDAR_EXCHANGE]
        if start:
            sql += " AND date >= %s"
            args.append(start)
        if end:
            sql += " AND date <= %s"
            args.append(end)
        sql += " ORDER BY date ASC"

        rows = self._connection.query(sql, args)
        open_days = [r["date"] for r in rows if _is_open(r.get("is_open"))]

        if count is not None:
            if start is not None:
                open_days = open_days[: int(count)]
            else:
                open_days = open_days[-int(count):]

        return [_as_datetime(d) for d in open_days]

    # -- get_all_securities / get_security_info ---------------------------

    def get_all_securities(
        self,
        types: Union[str, List[str]] = "stock",
        date: Optional[Union[str, datetime]] = None,
    ) -> pd.DataFrame:
        if isinstance(types, str):
            types = [types]

        # 本阶段仅支持 stock；其余类型（index/fund/etf）返回空结构（UNSUPPORTED，见 capabilities）
        if "stock" not in types:
            return pd.DataFrame(columns=_SECURITIES_COLUMNS)

        rows = self._connection.query(
            "SELECT ts_code, symbol, exchange, list_date, delist_date "
            "FROM ts_a_stock_list"
        )

        records = []
        for r in rows:
            ts_code = r["ts_code"]
            try:
                jq_code = to_joinquant_symbol(ts_code)
            except SymbolError:
                continue
            # ts_a_stock_list 无 name/display_name 列 -> 明确为 None（PARTIAL/LIMIT）
            records.append(
                {
                    "code": jq_code,
                    "display_name": None,
                    "name": None,
                    "start_date": pd.to_datetime(r["list_date"], errors="coerce"),
                    "end_date": pd.to_datetime(r["delist_date"], errors="coerce"),
                    "type": "stock",
                }
            )

        df = pd.DataFrame(records)
        if df.empty:
            df = pd.DataFrame(columns=["code"] + _SECURITIES_COLUMNS)
        else:
            df = df.set_index("code")

        # Point-in-Time：给定 date 时，仅保留在该日已上市且未退市的证券
        if date is not None:
            target = pd.to_datetime(date)
            start_dt = df["start_date"].fillna(pd.Timestamp.min)
            end_dt = df["end_date"].fillna(pd.Timestamp.max)
            df = df[(start_dt <= target) & (end_dt >= target)]

        return df[_SECURITIES_COLUMNS]

    def get_security_info(
        self,
        security: str,
        date: Optional[Union[str, datetime]] = None,
    ) -> Dict[str, Any]:
        _ = date  # 单证券元信息不依赖 date（上市/退市区间已由 list/delist_date 表达）
        ts_code = to_ts_symbol(security)
        row = self._connection.query_one(
            "SELECT ts_code, exchange, list_date, delist_date "
            "FROM ts_a_stock_list WHERE ts_code = %s",
            (ts_code,),
        )
        if row is None:
            return {}
        return {
            "type": "stock",
            "display_name": None,  # ts_a_stock_list 无 name 列
            "name": None,
            "start_date": pd.to_datetime(row["list_date"], errors="coerce"),
            "end_date": pd.to_datetime(row["delist_date"], errors="coerce"),
            "exchange": row.get("exchange"),
        }

    # -- 指数成分 / 权重（Point-in-Time） --------------------------------

    def _index_snapshot_date(self, index_code_ts: str, date) -> Optional[str]:
        """返回 <= date 的最近一个指数权重快照日；date 为 None 时取最新快照日。"""
        if date is not None:
            d = _fmt_date(date)
            row = self._connection.query_one(
                "SELECT MAX(trade_date) AS d FROM ts_index_weight "
                "WHERE index_code = %s AND trade_date <= %s",
                (index_code_ts, d),
            )
        else:
            row = self._connection.query_one(
                "SELECT MAX(trade_date) AS d FROM ts_index_weight WHERE index_code = %s",
                (index_code_ts,),
            )
        if row is None or row.get("d") is None:
            return None
        return _fmt_date(row["d"])

    def get_index_stocks(
        self,
        index_symbol: str,
        date: Optional[Union[str, datetime]] = None,
    ) -> List[str]:
        index_code_ts = normalize_index_symbol(index_symbol)
        snap = self._index_snapshot_date(index_code_ts, date)
        if snap is None:
            return []
        rows = self._connection.query(
            "SELECT stock_code FROM ts_index_weight "
            "WHERE index_code = %s AND trade_date = %s",
            (index_code_ts, snap),
        )
        result = []
        for r in rows:
            try:
                result.append(to_joinquant_symbol(r["stock_code"]))
            except SymbolError:
                continue
        return result

    def get_index_weights(
        self,
        index_id: str,
        date: Optional[Union[str, datetime]] = None,
    ) -> Dict[str, float]:
        index_code_ts = normalize_index_symbol(index_id)
        snap = self._index_snapshot_date(index_code_ts, date)
        if snap is None:
            return {}
        rows = self._connection.query(
            "SELECT stock_code, weight FROM ts_index_weight "
            "WHERE index_code = %s AND trade_date = %s",
            (index_code_ts, snap),
        )
        result: Dict[str, float] = {}
        for r in rows:
            try:
                code = to_joinquant_symbol(r["stock_code"])
            except SymbolError:
                continue
            try:
                result[code] = float(r["weight"])
            except (TypeError, ValueError):
                continue
        return result

    # -- 暂未实现（明确 NotImplemented，禁止返回虚假数据） ----------------

    def get_split_dividend(
        self,
        security: str,
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None,
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError(
            "InvestmentDataProvider: get_split_dividend 待 Phase 5 建设（公司行为 / 红利 / 拆股）"
        )

    def get_price(
        self,
        security: Union[str, List[str]],
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None,
        frequency: str = "daily",
        fields: Optional[List[str]] = None,
        skip_paused: bool = False,
        fq: str = "pre",
        count: Optional[int] = None,
        panel: bool = True,
        fill_paused: bool = True,
        pre_factor_ref_date: Optional[Union[str, datetime]] = None,
        prefer_engine: bool = False,
        force_no_engine: bool = False,
    ):
        raise NotImplementedError(
            "InvestmentDataProvider: get_price 待 Phase 2B 实现（基于 final_a_stock_eod_price 的日频原始价）"
        )
