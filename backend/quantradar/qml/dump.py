"""从 investment_data(Dolt) 导出 Qlib 可用的 qlib_data 目录。

设计约束（见 docs/00 核心原则：数据正确 > 防未来函数 > 会计正确 > 可复现）：
    - 只读：仅 SELECT，绝不写入 investment_data。
    - 防未来函数：每只证券仅取其 [start, end] 内的真实 OHLCV；不做任何前/后向填充伪造。
    - 宇宙（universe）：用 ts_a_stock_list 做 Point-in-Time 过滤
      （list_date <= start 且 delist_date 为空或 >= start），按 ts_code 确定性取前 N 只，
      避免幸存者偏差与随机抽样不确定性。
    - VWAP：表无 vwap 列，由真实 amount/volume 推导（Tushare 单位：amount=千元、volume=手
      → vwap(元/股) = amount*10/volume）。绝对量纲与 close 一致，Alpha158 的相对特征保持合理。
    - 使用 Qlib 自带的 FileCalendarStorage/FileInstrumentStorage/FileFeatureStorage 直接写
      二进制文件（与官方 DumpData 等价；本环境 qlib 0.9.7 的 DumpData 被裁剪，故手写）。

qlib_data 目录结构（provider_uri 根）：
    calendars/day.txt                交易日历（YYYY-MM-DD 一行）
    instruments/i_list.txt           市场名列表（含 "all"）
    instruments/all.txt              每只证券一行：code\\tstart\\tend
    features/<INST>/<FIELD>.day.bin  特征二进制（首 4 字节=start_index(float32)，其后 float32 值
                                     按全局 calendar 索引对齐，缺失为 NaN）
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from quantradar.providers.investment_data.connection import InvestmentDataConnection
from quantradar.providers.investment_data.symbols import (
    normalize_stock_symbol,
    to_joinquant_symbol,
)

# Qlib handler 需要的原始字段（Alpha158 依赖 $open/$high/$low/$close/$volume/$vwap）。
# 额外保留 amount 以与官方 investment_data 的 qlib 源字段（open/high/low/close/volume/amount/vwap）
# 保持一致（amount 不直接用于 Alpha158，但保留便于审计与后续扩展）。
_QLIB_FIELDS = ["open", "high", "low", "close", "volume", "amount", "vwap"]
_PRICE_COLS = ["open", "high", "low", "close", "volume", "amount"]


def _init_qlib_storage_module():
    """惰性导入 qlib 存储类（避免在无 qlib 环境强制依赖）。"""
    from qlib.data.storage.file_storage import (
        FileCalendarStorage,
        FileFeatureStorage,
        FileInstrumentStorage,
    )

    return FileCalendarStorage, FileInstrumentStorage, FileFeatureStorage


def select_universe(
    conn: InvestmentDataConnection,
    start: str,
    end: str,
    max_instruments: int = 300,
) -> List[str]:
    """Point-in-Time 宇宙：已上市且未退市，按 ts_code 确定性取前 N 只。

    返回 JQ 代码列表（如 600519.XSHG），既作 Qlib 标的名，也直接供 BulletTrade 使用。
    """
    rows = conn.query(
        "SELECT ts_code FROM ts_a_stock_list "
        "WHERE list_date <= %s AND (delist_date IS NULL OR delist_date >= %s) "
        "ORDER BY ts_code ASC LIMIT %s",
        (start, start, int(max_instruments)),
    )
    jq_list: List[str] = []
    for r in rows:
        ts_code = r["ts_code"]
        try:
            internal = normalize_stock_symbol(ts_code)
            jq = to_joinquant_symbol(internal)
        except Exception:  # 解析失败跳过，绝不静默接受非法代码
            continue
        jq_list.append(jq)
    return jq_list


def fetch_ohlcv(
    conn: InvestmentDataConnection,
    jq_symbols: List[str],
    start: str,
    end: str,
) -> Dict[str, pd.DataFrame]:
    """按证券分批拉取 OHLCV 并计算 vwap，返回 {JQ代码: DataFrame(index=datetime, fields)}。

    内部用 investment_data 行情表键（SH600519）查询；缺失/停牌日不补（显式 NaN）。
    """
    out: Dict[str, pd.DataFrame] = {}
    chunk = 50
    for i in range(0, len(jq_symbols), chunk):
        batch = jq_symbols[i : i + chunk]
        internal_batch = [normalize_stock_symbol(s) for s in batch]
        placeholders = ",".join(["%s"] * len(internal_batch))
        rows = conn.query(
            f"SELECT symbol, tradedate, open, high, low, close, volume, amount "
            f"FROM final_a_stock_eod_price WHERE symbol IN ({placeholders}) "
            f"AND tradedate BETWEEN %s AND %s ORDER BY symbol, tradedate ASC",
            tuple(internal_batch) + (start, end),
        )
        by_symbol: Dict[str, List[dict]] = {s: [] for s in batch}
        for r in rows:
            try:
                jq = to_joinquant_symbol(r["symbol"])
            except Exception:
                continue
            if jq in by_symbol:
                by_symbol[jq].append(r)
        for jq, recs in by_symbol.items():
            if not recs:
                continue
            df = pd.DataFrame(recs)
            df["tradedate"] = pd.to_datetime(df["tradedate"])
            df = df.set_index("tradedate").sort_index()
            df["vwap"] = (df["amount"].astype(float) * 10.0) / df["volume"].astype(float)
            df = df[_QLIB_FIELDS].astype(float)
            out[jq] = df
    return out


def build_qlib_data(
    target_dir: str,
    conn: Optional[InvestmentDataConnection] = None,
    start: str = "2018-01-01",
    end: str = "2024-12-31",
    max_instruments: int = 300,
    calendar_exchange: str = "SSE",
) -> Dict[str, Any]:
    """从 investment_data 构建 qlib_data 目录。

    Args:
        target_dir: qlib_data 输出根目录（provider_uri）。
        conn: 已连接的 InvestmentDataConnection；为 None 时按默认配置新建。
        start/end: 回测/训练窗口（含）。
        max_instruments: 宇宙上限（Point-in-Time 取前 N 只）。
        calendar_exchange: 交易日历交易所（SSE）。

    Returns:
        包含路径、交易日数、证券数、字段等的元信息字典（供审计）。
    """
    if conn is None:
        from quantradar.config import load_investment_data_config

        conn = InvestmentDataConnection(load_investment_data_config())

    FileCalendarStorage, FileInstrumentStorage, FileFeatureStorage = _init_qlib_storage_module()

    # File*Storage 构造会读 C["region"]，必须先 qlib.init 设置全局配置
    import qlib

    try:
        qlib.init(provider_uri={"day": target_dir}, region="cn")
    except Exception:
        pass

    os.makedirs(target_dir, exist_ok=True)
    os.makedirs(os.path.join(target_dir, "calendars"), exist_ok=True)
    os.makedirs(os.path.join(target_dir, "instruments"), exist_ok=True)
    os.makedirs(os.path.join(target_dir, "features"), exist_ok=True)

    # 1) 全局交易日历（is_open=1）
    cal_rows = conn.query(
        "SELECT date FROM ts_trade_day_calendar WHERE exchange=%s AND is_open=1 "
        "AND date BETWEEN %s AND %s ORDER BY date ASC",
        (calendar_exchange, start, end),
    )
    calendar = [r["date"].strftime("%Y-%m-%d") for r in cal_rows]
    if not calendar:
        raise RuntimeError(f"交易日历为空（exchange={calendar_exchange}, {start}~{end}）")

    # 2) 宇宙 + OHLCV
    universe = select_universe(conn, start, end, max_instruments=max_instruments)
    if not universe:
        raise RuntimeError("宇宙为空：无可交易证券（检查 start/end 与 ts_a_stock_list）")
    data = fetch_ohlcv(conn, universe, start, end)
    if not data:
        raise RuntimeError("OHLCV 拉取为空：investment_data 无匹配数据")

    cal_ts = pd.to_datetime(calendar)

    # 3) 写 calendar
    FileCalendarStorage(freq="day", future=False, provider_uri={"day": target_dir})._write_calendar(
        calendar
    )

    # 4) 写 instruments（Qlib 标准格式：code\tstart\tend）
    with open(os.path.join(target_dir, "instruments", "i_list.txt"), "w") as f:
        f.write("all\n")
    with open(os.path.join(target_dir, "instruments", "all.txt"), "w") as f:
        for inst, df in data.items():
            s = df.index.min().strftime("%Y-%m-%d")
            e = df.index.max().strftime("%Y-%m-%d")
            f.write(f"{inst}\t{s}\t{e}\n")

    # 5) 写 features（按全局 calendar 对齐，缺失 NaN）
    written_fields = 0
    for inst, df in data.items():
        aligned = df.reindex(cal_ts)
        for field in _QLIB_FIELDS:
            col = aligned[field].values.astype("<f")
            fs = FileFeatureStorage(
                instrument=inst, field=field, freq="day", provider_uri={"day": target_dir}
            )
            os.makedirs(os.path.dirname(fs.uri), exist_ok=True)
            fs.write(col, index=0)
            written_fields += 1

    meta = {
        "provider_uri": target_dir,
        "start": start,
        "end": end,
        "calendar_days": len(calendar),
        "instruments": len(data),
        "fields": _QLIB_FIELDS,
        "universe_sample": sorted(data.keys())[:10],
        "written_feature_files": written_fields,
    }
    return meta
