"""证券代码集中映射（InvestmentDataProvider 内部唯一转换入口）。

investment_data 现有多种代码格式，必须在此集中归一化，禁止在策略层散落多种格式：

    对外统一（JoinQuant 风格）：
        股票  600519.XSHG  000001.XSHE
        指数  000300.XSHG  399300.XSHE

    investment_data 内部格式：
        行情表（final_a_stock_eod_price / bao_a_stock_eod_info）：SH600519 / SZ000001
        ts_a_stock_list.symbol：000001（裸，缺交易所，需配合 exchange）
        ts_a_stock_list.ts_code：000001.SZ
        ts_index_weight.stock_code：000001.SZ
        ts_index_weight.index_code：000300.SH / 399300.SZ

本模块提供：
    normalize_stock_symbol(code)        -> SH600519 / SZ000001 （investment_data 行情表键）
    to_ts_symbol(code)                  -> 000001.SZ          （ts_a_stock_list / stock_code 键）
    to_joinquant_symbol(code)           -> 600519.XSHG
    to_investment_data_symbol(code)     == normalize_stock_symbol
    normalize_index_symbol(code)        -> 000300.SH          （ts_index_weight.index_code 键）
    to_joinquant_index_symbol(code)     -> 000300.XSHG

非法 / 无法解析的代码一律抛出 ValueError（禁止静默接受错误格式）。
"""

from __future__ import annotations

import re

# investment_data 行情表前缀（SH/SZ）+ 6 位数字的键
_STOCK_INTERNAL = re.compile(r"^(SH|SZ)(\d{6})$")
# Tushare / ts 风格后缀：600519.SH / 000001.SZ
_STOCK_TS = re.compile(r"^(\d{6})\.(SH|SZ)$")
# JoinQuant 风格后缀：600519.XSHG / 000001.XSHE
_STOCK_JQ = re.compile(r"^(\d{6})\.(XSHG|XSHE)$")

# 指数：ts_index_weight 使用 .SH / .SZ 后缀
_INDEX_TS = re.compile(r"^(\d{6})\.(SH|SZ)$")
_INDEX_JQ = re.compile(r"^(\d{6})\.(XSHG|XSHE)$")


class SymbolError(ValueError):
    """证券代码无法解析。"""


def _require_stock_internal(code: str) -> str:
    m = _STOCK_INTERNAL.match(code)
    if not m:
        raise SymbolError(f"无法解析为 investment_data 股票代码: {code!r}")
    return code


def normalize_stock_symbol(code: str) -> str:
    """任意可接受格式 -> investment_data 行情表键（SH600519 / SZ000001）。"""
    if code is None:
        raise SymbolError("代码不能为 None")
    code = code.strip().upper()
    if not code:
        raise SymbolError("代码不能为空")

    m = _STOCK_INTERNAL.match(code)
    if m:
        return code

    m = _STOCK_TS.match(code)
    if m:
        num, ex = m.groups()
        return f"{ex}{num}"

    m = _STOCK_JQ.match(code)
    if m:
        num, ex = m.groups()
        prefix = "SH" if ex == "XSHG" else "SZ"
        return f"{prefix}{num}"

    raise SymbolError(f"无法解析股票代码: {code!r}")


def to_ts_symbol(code: str) -> str:
    """任意可接受格式 -> Tushare/ts 风格（000001.SZ）。"""
    ex, num = _STOCK_INTERNAL.match(normalize_stock_symbol(code)).groups()
    return f"{num}.{ex}"


def to_joinquant_symbol(code: str) -> str:
    """任意可接受格式 -> JoinQuant 风格（600519.XSHG / 000001.XSHE）。"""
    ex, num = _STOCK_INTERNAL.match(normalize_stock_symbol(code)).groups()
    return f"{num}.XSHG" if ex == "SH" else f"{num}.XSHE"


def to_investment_data_symbol(code: str) -> str:
    """别名：等价于 normalize_stock_symbol（行情表键）。"""
    return normalize_stock_symbol(code)


def normalize_index_symbol(code: str) -> str:
    """任意可接受格式 -> ts_index_weight.index_code 风格（000300.SH / 399300.SZ）。"""
    if code is None:
        raise SymbolError("指数代码不能为 None")
    code = code.strip().upper()
    if not code:
        raise SymbolError("指数代码不能为空")

    m = _INDEX_TS.match(code)
    if m:
        return code

    m = _INDEX_JQ.match(code)
    if m:
        num, ex = m.groups()
        suffix = "SH" if ex == "XSHG" else "SZ"
        return f"{num}.{suffix}"

    raise SymbolError(f"无法解析指数代码: {code!r}")


def to_joinquant_index_symbol(code: str) -> str:
    """任意可接受格式 -> JoinQuant 指数风格（000300.XSHG / 399300.XSHE）。"""
    num, ex = normalize_index_symbol(code).split(".")
    return f"{num}.XSHG" if ex == "SH" else f"{num}.XSHE"
