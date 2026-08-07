from jqdata import *  # noqa: F401,F403

import datetime as _dt
import pandas as _pd

from bullet_trade.core.exceptions import FutureDataError


def _record_error(message):
    g.errors.append(message)


def _expect_future_error(label, func, *args, **kwargs):
    try:
        func(*args, **kwargs)
    except FutureDataError:
        return
    except Exception as exc:
        _record_error(f"{label} 返回异常: {exc}")
    else:
        _record_error(f"{label} 未触发 FutureDataError")


def _expect_type(label, value, types):
    if not isinstance(value, types):
        _record_error(f"{label} 类型不符合预期: {type(value)}")


def _summarize_value(value):
    if value is None:
        return "None"
    if isinstance(value, _pd.DataFrame):
        head_preview = value.head(2).to_dict(orient="records") if not value.empty else []
        return f"DataFrame shape={value.shape} columns={list(value.columns)[:6]} head={head_preview}"
    if isinstance(value, dict):
        return f"dict keys={list(value.keys())[:6]}"
    if isinstance(value, (list, tuple)):
        return f"{type(value).__name__} len={len(value)}"
    return f"{type(value).__name__} value={value}"


def _safe_call(label, func, *args, **kwargs):
    try:
        result = func(*args, **kwargs)
        log.info("[数据API] %s args=%s kwargs=%s result=%s", label, args, kwargs, _summarize_value(result))
        return result
    except Exception as exc:
        _record_error(f"{label} 调用失败: {exc}")
        return None


def initialize(context):
    set_option('avoid_future_data', True)
    set_option('use_real_price', True)
    set_data_provider('jqdata')
    set_universe(['000001.XSHE', '000300.XSHG'])
    g.errors = []
    g.security = '000001.XSHE'
    g.index = '000300.XSHG'
    try:
        import jqdatasdk as _jq
        g.query = _jq.query(_jq.valuation.code, _jq.valuation.market_cap).limit(1)
    except Exception:
        g.query = None


def before_trading_start(context):
    future_date = context.current_dt.date() + _dt.timedelta(days=1)
    _expect_future_error(
        "get_price_future",
        get_price,
        g.security,
        end_date=future_date,
        frequency='daily',
        fields=['close'],
    )
    _expect_future_error("get_all_securities_future", get_all_securities, 'stock', future_date)
    _expect_future_error("get_index_stocks_future", get_index_stocks, g.index, future_date)
    _expect_future_error("get_trade_days_future", get_trade_days, end_date=future_date)
    _expect_future_error("get_extras_future", get_extras, 'is_st', [g.security], end_date=future_date)
    _expect_future_error("get_billboard_list_future", get_billboard_list, end_date=future_date)

    _expect_future_error(
        "get_price_preopen_close",
        get_price,
        g.security,
        end_date=context.current_dt,
        frequency='daily',
        fields=['close'],
    )
    _expect_future_error(
        "get_extras_preopen",
        get_extras,
        'paused',
        [g.security],
        end_date=context.current_dt.date(),
    )
    if g.query is not None:
        _expect_future_error(
            "get_fundamentals_preopen",
            get_fundamentals,
            g.query,
            date=context.current_dt.date(),
        )
        _expect_future_error(
            "get_fundamentals_continuously_preopen",
            get_fundamentals_continuously,
            g.query,
            end_date=context.current_dt.date(),
        )


def handle_data(context, data):
    _expect_future_error(
        "get_price_intraday_close",
        get_price,
        g.security,
        end_date=context.current_dt,
        frequency='daily',
        fields=['close'],
    )
    ok_price = _safe_call(
        "get_price_intraday_open",
        get_price,
        g.security,
        end_date=context.current_dt,
        frequency='daily',
        fields=['open'],
    )
    if ok_price is not None:
        _expect_type("get_price_intraday_open", ok_price, _pd.DataFrame)

    bars = _safe_call("get_bars", get_bars, g.security, 5, unit='1d', df=True)
    if bars is not None:
        _expect_type("get_bars", bars, _pd.DataFrame)

    ticks = _safe_call("get_ticks", get_ticks, g.security, end_dt=context.current_dt, count=1, df=True)
    if ticks is not None:
        _expect_type("get_ticks", ticks, _pd.DataFrame)

    tick = _safe_call("get_current_tick", get_current_tick, g.security, dt=context.current_dt)
    if tick is not None:
        _expect_type("get_current_tick", tick, dict)

    current_data = _safe_call("get_current_data", get_current_data)
    if current_data is not None and g.security in current_data:
        unit = current_data[g.security]
        if not hasattr(unit, 'last_price'):
            _record_error("get_current_data 未返回 last_price 字段")

    hist = _safe_call("history", history, 3, unit='1d', field='close', security_list=[g.security], df=True)
    if hist is not None:
        _expect_type("history", hist, _pd.DataFrame)


def after_trading_end(context):
    price = _safe_call(
        "get_price_after_close",
        get_price,
        g.security,
        end_date=context.current_dt,
        frequency='daily',
        fields=['close'],
    )
    if price is not None:
        _expect_type("get_price_after_close", price, _pd.DataFrame)

    _safe_call("get_trade_days", get_trade_days, end_date=context.current_dt, count=1)
    _safe_call("get_trade_day", get_trade_day, g.security, context.current_dt)
    _safe_call("get_all_securities", get_all_securities, 'stock', context.current_dt.date())
    _safe_call("get_security_info", get_security_info, g.security, context.current_dt.date())
    fund_df = _safe_call("get_all_securities_fund", get_all_securities, 'fund', context.current_dt.date())
    fund_code = None
    if isinstance(fund_df, _pd.DataFrame) and not fund_df.empty:
        for code in fund_df.index:
            if str(code).endswith(".OF"):
                fund_code = code
                break
    if fund_code is None:
        for candidate in ("000001.OF", "000200.OF"):
            fund_code = candidate
            break
    if fund_code:
        _safe_call("get_fund_info", get_fund_info, fund_code, context.current_dt.date())
    else:
        _record_error("get_fund_info 无可用场外基金标的")
    _safe_call("get_index_stocks", get_index_stocks, g.index, context.current_dt.date())
    _safe_call("get_index_weights", get_index_weights, g.index, context.current_dt.date())
    _safe_call("get_industry_stocks", get_industry_stocks, "J66", context.current_dt.date())
    _safe_call("get_industry", get_industry, g.security, context.current_dt.date())

    concept = _safe_call("get_concept", get_concept, g.security, context.current_dt.date())
    concept_code = None
    if isinstance(concept, dict):
        info = concept.get(g.security, {})
        concepts = info.get('jq_concept') if isinstance(info, dict) else None
        if concepts:
            concept_code = concepts[0].get('concept_code')
    if concept_code:
        _safe_call("get_concept_stocks", get_concept_stocks, concept_code, context.current_dt.date())

    _safe_call("get_margincash_stocks", get_margincash_stocks, context.current_dt.date())
    _safe_call("get_marginsec_stocks", get_marginsec_stocks, context.current_dt.date())
    _safe_call("get_dominant_future", get_dominant_future, "IF", context.current_dt.date())
    _safe_call("get_future_contracts", get_future_contracts, "IF", context.current_dt.date())
    _safe_call("get_billboard_list", get_billboard_list, stock_list=[g.security], end_date=context.current_dt.date())
    _safe_call(
        "get_locked_shares",
        get_locked_shares,
        [g.security],
        start_date=context.current_dt.date(),
        end_date=context.current_dt.date(),
    )

    _safe_call("get_extras", get_extras, 'is_st', [g.security], end_date=context.current_dt.date())
    if g.query is not None:
        _safe_call("get_fundamentals", get_fundamentals, g.query, date=context.current_dt.date())
        _safe_call(
            "get_fundamentals_continuously",
            get_fundamentals_continuously,
            g.query,
            end_date=context.current_dt.date(),
        )

    if g.errors:
        raise AssertionError("数据 API 校验失败:\\n" + "\\n".join(g.errors))
