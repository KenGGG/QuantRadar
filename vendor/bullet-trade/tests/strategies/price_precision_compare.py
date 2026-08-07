"""
盘中分钟价小数位与前复权基准价对比。

用于在本地回测与聚宽环境输出同样的检查结果，便于对齐差异。
"""
from jqdata import *  # noqa: F401,F403

import numpy as np
import pandas as pd


STOCK_CODE = "300640.XSHE"
FUND_CODE = "511880.XSHG"
TARGET_DATE = "2024-04-01"


def _maybe_set_data_provider():
    setter = globals().get("set_data_provider")
    if callable(setter):
        try:
            setter("jqdata")
        except Exception:
            pass


def _init_results():
    g.results = {
        "minute_checks": [],
        "pre_close": None,
        "errors": [],
    }
    g._minute_checked = False
    g._pre_checked = False
    g._factor_checked = False


def _record_error(message):
    g.results["errors"].append(message)
    log.error(message)


def _infer_decimals(code):
    info = None
    try:
        info = get_security_info(code)
    except Exception:
        info = None

    for attr in ("price_decimals", "tick_decimals"):
        if info is not None and hasattr(info, attr):
            try:
                val = int(getattr(info, attr))
                if val >= 0:
                    return val
            except Exception:
                pass

    if isinstance(info, dict):
        for key in ("price_decimals", "tick_decimals"):
            val = info.get(key)
            if isinstance(val, (int, float)) and val >= 0:
                return int(val)
        category = info.get("category") or info.get("type")
    else:
        category = getattr(info, "category", None) or getattr(info, "type", None)

    if category and str(category).lower() in ("fund", "money_market_fund", "etf"):
        return 3
    if code.startswith("511"):
        return 3
    return 2


def _extract_close(df):
    if df is None:
        return None
    try:
        if df.empty:
            return None
    except Exception:
        pass

    try:
        value = df.iloc[-1]["close"]
    except Exception:
        try:
            value = df.iloc[-1][0]
        except Exception:
            return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    try:
        return float(value)
    except Exception:
        return None


def _extract_field(df, field, code=None):
    if df is None:
        return None
    try:
        if df.empty:
            return None
    except Exception:
        pass

    try:
        if isinstance(df, pd.Series):
            value = df.get(field)
            if pd.isna(value):
                return None
            return float(value)
    except Exception:
        pass

    try:
        if isinstance(df, pd.DataFrame):
            if isinstance(df.columns, pd.MultiIndex):
                if code is not None:
                    if (field, code) in df.columns:
                        value = df[(field, code)].iloc[-1]
                        return float(value) if pd.notna(value) else None
                    if (code, field) in df.columns:
                        value = df[(code, field)].iloc[-1]
                        return float(value) if pd.notna(value) else None
                try:
                    block = df.xs(field, axis=1, level=0)
                except Exception:
                    try:
                        block = df.xs(field, axis=1, level=1)
                    except Exception:
                        block = None
                if block is not None and not block.empty:
                    if code is not None and code in block.columns:
                        value = block[code].iloc[-1]
                    else:
                        value = block.iloc[-1][0]
                    return float(value) if pd.notna(value) else None

            if "code" in df.columns and "time" in df.columns and field in df.columns:
                if code is not None:
                    sub = df[df["code"] == code]
                    if sub.empty:
                        return None
                    value = sub.iloc[-1][field]
                else:
                    value = df.iloc[-1][field]
                return float(value) if pd.notna(value) else None

            if field in df.columns:
                value = df.iloc[-1][field]
                return float(value) if pd.notna(value) else None
    except Exception:
        return None

    return None


def _describe_df(df):
    if df is None:
        return "None"
    if not isinstance(df, pd.DataFrame):
        return f"type={type(df)}"
    try:
        columns = list(df.columns)
    except Exception:
        columns = "unknown"
    try:
        index = df.index
        if isinstance(index, pd.MultiIndex):
            index_names = list(index.names)
        else:
            index_names = index.name
    except Exception:
        index_names = "unknown"
    return f"shape={df.shape}, cols={columns}, index={index_names}"


def initialize(context):
    set_option("avoid_future_data", True)
    set_option("use_real_price", True)
    set_option("force_no_engine", True)
    set_benchmark("000300.XSHG")

    _maybe_set_data_provider()
    _init_results()

    g.targets = [STOCK_CODE, FUND_CODE]
    run_daily(check_minute_close, time="14:25")
    run_daily(check_pre_close, time="close")


def check_minute_close(context):
    if getattr(g, "_minute_checked", False):
        return
    g._minute_checked = True
    from datetime import timedelta
    start_time = context.current_dt - timedelta(minutes=2)
    for code in g.targets:
        try:
            df = get_price(
                security=code,
                end_date=context.current_dt,
                frequency="minute",
                fields=["close"],
                count=1,
                fq="pre",
            )
            raw_close = _extract_close(df)
            if raw_close is None:
                _record_error(f"分钟行情为空: {code}")
                continue

            decimals = _infer_decimals(code)
            rounded = float(np.round(raw_close, decimals))
            diff = abs(raw_close - rounded)
            payload = {
                "code": code,
                "raw_close": raw_close,
                "rounded_close": rounded,
                "decimals": decimals,
                "diff": diff,
                "time": str(context.current_dt),
            }
            g.results["minute_checks"].append(payload)
            log.info(
                "[精度对比][分钟] %s raw=%.6f rounded=%.6f decimals=%s diff=%.10f",
                code,
                raw_close,
                rounded,
                decimals,
                diff,
            )
        except Exception as exc:
            _record_error(f"分钟行情失败 {code}: {exc}")


def check_pre_close(context):
    if getattr(g, "_pre_checked", False):
        return
    g._pre_checked = True

    try:
        df = get_price(
            security=STOCK_CODE,
            end_date=TARGET_DATE,
            frequency="daily",
            fields=["close"],
            count=1,
            fq="pre",
        )
        raw_close = _extract_close(df)
        if raw_close is None:
            _record_error(f"前复权行情为空: {STOCK_CODE}")
            return

        decimals = _infer_decimals(STOCK_CODE)
        rounded = float(np.round(raw_close, decimals))
        g.results["pre_close"] = {
            "code": STOCK_CODE,
            "raw_close": raw_close,
            "rounded_close": rounded,
            "decimals": decimals,
            "target_date": TARGET_DATE,
            "context_date": str(context.current_dt.date()),
        }
        log.info(
            "[精度对比][前复权] %s date=%s raw=%.6f rounded=%.6f decimals=%s ref=%s",
            STOCK_CODE,
            TARGET_DATE,
            raw_close,
            rounded,
            decimals,
            context.current_dt.date(),
        )
        _log_factor_probe(context)
    except Exception as exc:
        _record_error(f"前复权行情失败 {STOCK_CODE}: {exc}")


def _log_factor_probe(context):
    if getattr(g, "_factor_checked", False):
        return
    g._factor_checked = True

    try:
        df_raw = get_price(
            security=STOCK_CODE,
            end_date=TARGET_DATE,
            frequency="daily",
            fields=["close", "factor"],
            count=1,
            fq=None,
        )
        raw_close = _extract_field(df_raw, "close", STOCK_CODE)
        raw_factor = _extract_field(df_raw, "factor", STOCK_CODE)
        log.info(
            "[精度对比][因子] %s 目标日=%s close=%s factor=%s df=%s",
            STOCK_CODE,
            TARGET_DATE,
            raw_close,
            raw_factor,
            _describe_df(df_raw),
        )
    except Exception as exc:
        log.warning("[精度对比][因子] 目标日因子获取失败: %s", exc)
        raw_close = None
        raw_factor = None

    try:
        ref_dt = context.current_dt
        df_ref = get_price(
            security=STOCK_CODE,
            end_date=ref_dt,
            frequency="daily",
            fields=["factor"],
            count=1,
            fq=None,
        )
        ref_factor = _extract_field(df_ref, "factor", STOCK_CODE)
        log.info(
            "[精度对比][因子] %s 参考日=%s factor=%s df=%s",
            STOCK_CODE,
            ref_dt.date(),
            ref_factor,
            _describe_df(df_ref),
        )
        if raw_close is not None and raw_factor is not None and ref_factor:
            ratio = raw_factor / ref_factor
            inferred = raw_close * ratio
            log.info(
                "[精度对比][因子] %s 推算前复权 close=%.6f ratio=%.6f",
                STOCK_CODE,
                inferred,
                ratio,
            )
    except Exception as exc:
        log.warning("[精度对比][因子] 参考日因子获取失败: %s", exc)
