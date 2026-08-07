"""InvestmentDataProvider —— investment_data（Dolt 只读）的 BulletTrade DataProvider 实现。

Phase 2A 范围（仅基础能力与历史时点查询，禁止伪造 / 禁止写操作）：
    - 只读连接（connection.py）
    - 证券代码映射（symbols.py）
    - get_trade_days
    - get_all_securities（Point-in-Time）
    - get_security_info
    - get_index_stocks（Point-in-Time）
    - get_index_weights（Point-in-Time）
    - get_price（fq='none' 日频原始价；Phase 2B）
    - get_split_dividend：本阶段显式 NotImplementedError（Phase 5）

数据正确性优先：所有历史查询按 date 截断到「当时可得」，避免未来函数与幸存者偏差。
缺数据（如证券 display_name）明确标记 PARTIAL/LIMIT，绝不默认填充正常值。
"""

from __future__ import annotations

from collections import defaultdict
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
    normalize_stock_symbol,
    to_joinquant_symbol,
    to_ts_symbol,
)

# final_a_stock_eod_price 原表字段（fq='none' 直接用这些；adjclose 绝不用于原始价）
_PRICE_TABLE = "final_a_stock_eod_price"
_PRICE_FIELDS = ["open", "high", "low", "close", "volume", "amount"]
_PRICE_DATE_COL = "tradedate"

# 涨跌停来源表（final_a_stock_limit；真实数据，绝不伪造）
_LIMIT_TABLE = "final_a_stock_limit"
_LIMIT_FIELDS = ["up_limit", "down_limit"]

# 用户字段名（JoinQuant 约定）-> investment_data 内部列名（价格表 / 涨跌停表）
_FIELD_TO_COLUMN = {
    "money": "amount",
    "high_limit": "up_limit",
    "low_limit": "down_limit",
}
# 计算字段（无独立存储列，由其他字段派生；绝不伪造）
_COMPUTED_FIELDS = {"paused"}

# JoinQuant 频率别名 -> investment_data 内部表达（Phase 3 JQ 兼容核心）
_FREQUENCY_ALIASES = {"d": "daily", "day": "daily", "1d": "daily"}
# 复权在 Phase 5；本阶段 fq='pre'/'post' 仅作为「未调整（LIMIT）」等价 raw 透传，
# 绝不伪造复权因子；其余未知 fq 仍 NotImplementedError。
_FQ_RAW_ALIASES = {"pre", "post", "qfq", "hfq", "pre-forward", "post-forward"}

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
        fq: str = "none",
        count: Optional[int] = None,
        panel: bool = True,
        fill_paused: bool = True,
        pre_factor_ref_date: Optional[Union[str, datetime]] = None,
        prefer_engine: bool = False,
        force_no_engine: bool = False,
    ) -> pd.DataFrame:
        """日频原始行情（JoinQuant 兼容核心，Phase 3）。

        数据源：final_a_stock_eod_price（列 tradedate / symbol / open / high / low /
        close / volume / amount）。严禁读取 adjclose 冒充原始价。

        约定：
            - frequency 别名归一：'d'/'day'/'1d' -> 'daily'；其余抛 NotImplementedError（分钟级 UNSUPPORTED）。
            - fq 别名：'none'/None -> 原始价（PASS）；'pre'/'post'/'qfq'/'hfq' 等 ->
              当前等价原始价（LIMIT，复权因子实现在 Phase 5，绝不伪造）；其余未知 fq 抛 NotImplementedError。
            - 字段别名（JoinQuant -> investment_data）：'money' -> 'amount'。
            - security 支持 str 或 List[str]，经 normalize_stock_symbol 转 SH600519 查表。
            - 单证券：返回 DataFrame，index=日期，columns=字段（扁平）。
            - 多证券 panel=True：返回 DataFrame，index=日期，columns=MultiIndex(字段, 证券)。
            - count 与 start/end 组合：无边界（start/end/count 全 None）明确抛 ValueError，
              避免全表扫描；count 优先按交易日历截断（见 get_trade_days）。
            - 缺行（停牌 / 退市 / 上市前）不做任何回填或伪造；对应位置为 NaN/空，
              调用方应据此识别 PARTIAL，禁止假装完整。
        """
        # 频率别名归一
        frequency = _FREQUENCY_ALIASES.get(frequency, frequency)
        if frequency != "daily":
            raise NotImplementedError(
                "InvestmentDataProvider: 仅支持日频（frequency='daily'）；"
                "分钟级 UNSUPPORTED"
            )
        # fq 归一：None 视为 'none'；pre/post 等视为未调整（LIMIT，Phase 5 复权）
        fq = (fq or "none").lower()
        if fq != "none" and fq not in _FQ_RAW_ALIASES:
            raise NotImplementedError(
                f"InvestmentDataProvider: 未知复权方式（fq={fq!r}）；"
                "本阶段仅支持 fq='none'（及 pre/post 等价原始价的 LIMIT 透传），复权待 Phase 5"
            )

        # 归一化 securities -> 有序映射 {jq_code: internal_symbol}
        if isinstance(security, str):
            securities = [security]
        else:
            securities = list(security)
        if not securities:
            raise SymbolError("get_price: security 不能为空列表")

        jq_to_internal: "dict[str, str]" = {}
        for s in securities:
            internal = normalize_stock_symbol(s)
            jq_to_internal[to_joinquant_symbol(internal)] = internal

        # 字段解析（JoinQuant -> investment_data 内部列；区分价格表 / 涨跌停表 / 计算字段）
        price_cols: List[str] = []
        limit_cols: List[str] = []
        need_paused = False
        rename_back: Dict[str, str] = {}  # 内部列名 -> 对外字段名
        requested_raw = list(fields) if fields else list(_PRICE_FIELDS)
        available = set(_PRICE_FIELDS) | set(_LIMIT_FIELDS) | _COMPUTED_FIELDS | set(_FIELD_TO_COLUMN.keys())
        for f in requested_raw:
            if f in _COMPUTED_FIELDS:
                need_paused = True
                continue
            internal = _FIELD_TO_COLUMN.get(f, f)
            if internal in _PRICE_FIELDS:
                price_cols.append(internal)
                if internal != f:
                    rename_back[internal] = f
            elif internal in _LIMIT_FIELDS:
                limit_cols.append(internal)
                rename_back[internal] = f
            else:
                raise ValueError(
                    f"get_price: 不支持的字段 {f!r}；"
                    f"可用字段={_PRICE_FIELDS} + high_limit/low_limit/paused（money->amount）"
                )
        # paused 由 volume 派生；若未显式请求 volume 仍内部取用，最后按需剔除
        volume_requested = "volume" in requested_raw
        # 价格表必须至少有一列作为日期锚点（即便只请求了涨跌停 / paused）
        if not price_cols:
            price_cols.append("volume")
        if need_paused and "volume" not in price_cols:
            price_cols.append("volume")
        drop_volume = (not volume_requested) and ("volume" in price_cols)

        # 边界守卫：避免无约束的全表扫描
        if start_date is None and end_date is None and count is None:
            raise ValueError(
                "get_price: 必须指定 start_date / end_date 或 count 之一"
            )

        ordered_jq = list(jq_to_internal.keys())
        per_security: Dict[str, pd.DataFrame] = {}
        for jq, internal in jq_to_internal.items():
            df = self._fetch_raw_price(
                internal, price_cols, limit_cols, need_paused,
                start_date, end_date, count, fill_paused,
            )
            if drop_volume and "volume" in df.columns:
                df = df.drop(columns=["volume"])
            if rename_back:
                df = df.rename(columns=rename_back)
            per_security[jq] = df

        # 单证券：扁平 columns
        if len(ordered_jq) == 1:
            return per_security[ordered_jq[0]]

        # 多证券：columns = MultiIndex(字段, 证券)
        frames = [per_security[jq] for jq in ordered_jq]
        # 先按证券拼接（level0=证券），再交换到 (字段, 证券)
        combined = pd.concat(
            frames, axis=1, keys=ordered_jq, names=["security", "field"]
        )
        combined = combined.swaplevel(0, 1, axis=1).sort_index(axis=1)
        return combined

    def _fetch_table_cols(
        self,
        table: str,
        cols: List[str],
        internal_symbol: str,
        start: Optional[str],
        end: Optional[str],
        count: Optional[int],
        fill_paused: bool,
        symbol_col: str = "symbol",
    ) -> pd.DataFrame:
        """从给定表拉取单证券指定列的原始日频，返回 index=日期的 DataFrame。

        不做任何复权 / 数值伪造；缺行即缺（NaN 或空行），由上层识别 PARTIAL。
        """
        if not cols:
            return pd.DataFrame(index=pd.DatetimeIndex([]))

        col_sql = ", ".join(cols)
        sql = (
            f"SELECT tradedate, {col_sql} FROM {table} "
            f"WHERE {symbol_col} = %s"
        )
        args: List[Any] = [internal_symbol]
        if start:
            sql += " AND tradedate >= %s"
            args.append(start)
        if end:
            sql += " AND tradedate <= %s"
            args.append(end)

        # count 优先：未给定 start 时取窗口内「最近 N 日」（DESC+LIMIT 再翻转）；
        # 给定 start 时取「自 start 起前 N 日」（ASC+LIMIT）——与 JoinQuant 语义一致。
        if count is not None:
            count = int(count)
            if start:
                sql += " ORDER BY tradedate ASC LIMIT %s"
            else:
                sql += " ORDER BY tradedate DESC LIMIT %s"
            args.append(count)
            rows = self._connection.query(sql, args)
            if not start:
                rows.reverse()  # 回到升序
        else:
            sql += " ORDER BY tradedate ASC"
            rows = self._connection.query(sql, args)

        if not rows:
            # 显式空（上市前 / 退市后 / 无数据窗口）—— 不伪造
            empty_idx = pd.DatetimeIndex([])
            return pd.DataFrame(
                {c: pd.Series(dtype="float64") for c in cols}, index=empty_idx
            )

        dates = pd.to_datetime([r["tradedate"] for r in rows])
        data = {
            c: [float(r[c]) if r[c] is not None else float("nan") for r in rows]
            for c in cols
        }
        df = pd.DataFrame(data, index=pd.DatetimeIndex(dates))

        if fill_paused and start and end:
            # 仅当显式给定闭合窗口时，才对齐到交易日历并将停牌/缺行日置为 NaN
            # （显式 PARTIAL，绝不向前填充制造价格）。无边界时不扩展，避免全历史扫描。
            cal = self.get_trade_days(start, end)
            if cal:
                cal_idx = pd.DatetimeIndex([pd.Timestamp(d).normalize() for d in cal])
                df = df.reindex(cal_idx)
        return df

    def _fetch_raw_price(
        self,
        internal_symbol: str,
        price_cols: List[str],
        limit_cols: List[str],
        need_paused: bool,
        start_date: Optional[Union[str, datetime]],
        end_date: Optional[Union[str, datetime]],
        count: Optional[int],
        fill_paused: bool,
    ) -> pd.DataFrame:
        """从 final_a_stock_eod_price（价格）+ final_a_stock_limit（涨跌停）拉取单证券日频，
        并可选派生 paused。返回 index=日期、列为请求字段（含 limit/paused）的 DataFrame。

        涨跌停来自真实表（final_a_stock_limit）；paused 由 volume==0 派生；
        缺数据显式 NaN（PARTIAL），绝不伪造。
        """
        start = _fmt_date(start_date)
        end = _fmt_date(end_date)

        # 价格表（主表，决定返回日期索引）
        price_df = self._fetch_table_cols(
            _PRICE_TABLE, price_cols, internal_symbol, start, end, count, fill_paused
        )

        result = price_df
        if limit_cols:
            # 涨跌停表按相同窗口取全量（忽略 count），再对齐到价格表日期索引
            limit_df = self._fetch_table_cols(
                _LIMIT_TABLE, limit_cols, internal_symbol, start, end, None, False
            )
            limit_df = limit_df.reindex(price_df.index)
            result = price_df.join(limit_df, how="left")

        if need_paused:
            vol = result["volume"] if "volume" in result.columns else pd.Series(
                0.0, index=result.index
            )
            # volume 缺失或为 0 视为停牌（真实信号）；有成交价的交易日视为未停牌
            result["paused"] = (vol.fillna(0) == 0)

        return result
