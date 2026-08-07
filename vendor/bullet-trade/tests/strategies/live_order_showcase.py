"""
官方示例：演示聚宽常用下单 API 在 BulletTrade 中的实盘/回测行为。

覆盖能力：
- `order` / `MarketOrderStyle`（含保护价、科创限价） / `LimitOrderStyle`；
- `order_target` / `order_value` / `order_target_value`；
- 限价单自行根据行情和价格笼子选择价格；
- 卖出前检查可用仓位，交易后调用 `print_portfolio_info` 查看效果；
- 日志提示同步/异步：`TRADE_MAX_WAIT_TIME>0` 等待回报，=0 即刻返回。

策略仅用于演示，不构成投资建议。
"""

from jqdata import *
import asyncio
import datetime



def initialize(context):
    g.symbols = {
        "gold": "518880.XSHG",
        "nasdaq": "513100.XSHG",
        "cash": "511880.XSHG",
        "pingan": "601318.XSHG",
    }
    g.market_lot = 100
    set_benchmark(g.symbols["pingan"])
    set_option("use_real_price", True)


    # 启动后约 1 分钟触发所有示例任务，单次触发内顺序执行，每个任务间隔 1s
    base_time = datetime.datetime.now() + datetime.timedelta(seconds=60)
    time_fmt = "%H:%M"
    #run_daily(schedule_all_examples_sequential, time=base_time.strftime(time_fmt))
    run_daily(schedule_every_minute, time="every_minute")
    run_daily(schedule_market_order, time=base_time.strftime(time_fmt))
    #run_daily(schedule_cancel_example, time=base_time.strftime(time_fmt))

def after_code_changed(context):
    log.info(f'============代码变更后运行after_code_changed：{context.current_dt.time()}============')
    g.market_lot = 100
    g.symbols = {
        "gold": "518880.XSHG",
        "nasdaq": "513100.XSHG",
        "cash": "511880.XSHG",
        "pingan": "601318.XSHG",
    }

    unschedule_all()
    # 启动后约 1 分钟触发所有示例任务，单次触发内顺序执行，每个任务间隔 1s
    base_time = datetime.datetime.now() + datetime.timedelta(seconds=60)
    time_fmt = "%H:%M"
    #run_daily(schedule_all_examples_sequential, time=base_time.strftime(time_fmt))
    run_daily(schedule_every_minute, time="every_minute")
    run_daily(schedule_market_order, time=base_time.strftime(time_fmt))
    run_daily(schedule_cancel_example, time=base_time.strftime(time_fmt))
    run_daily(schedule_market_order_examples, time=base_time.strftime(time_fmt))
    run_daily(schedule_market_order_sell, time=base_time.strftime(time_fmt))
    run_daily(schedule_async_market_burst, time=base_time.strftime(time_fmt))
    run_daily(schedule_market_order_async, time=base_time.strftime(time_fmt))
    run_daily(schedule_target_api_examples, time=base_time.strftime(time_fmt))
    run_daily(schedule_limit_value_examples, time=base_time.strftime(time_fmt))
    run_daily(schedule_cash_position_housekeeping, time=base_time.strftime(time_fmt))
    run_daily(schedule_pingan_rotation, time=base_time.strftime(time_fmt))


# async def schedule_all_examples_sequential(context):
#     """在同一时间点顺序触发所有示例，每个间隔 1s。"""
#     tasks = [
#         schedule_market_order_1,
#         schedule_market_order_examples,
#         schedule_target_api_examples,
#         schedule_limit_value_examples,
#         schedule_cash_position_housekeeping,
#         schedule_pingan_rotation,
#         schedule_async_market_burst,
#         schedule_cancel_example,
#         schedule_t0_roundtrip,
#     ]
#     for func in tasks:
#         try:
#             func(context)
#         except Exception as exc:
#             log.error(f"示例任务 {func.__name__} 执行异常: {exc}")
#         await asyncio.sleep(20)


# def _next_rounded_minute(after_seconds: int = 60) -> datetime.datetime:
#     """保留兼容函数，当前未使用。"""
#     target = datetime.datetime.now() + datetime.timedelta(seconds=after_seconds)
#     rounded = target.replace(second=0, microsecond=0)
#     if rounded <= target:
#         rounded += datetime.timedelta(minutes=1)
#     return rounded

def schedule_every_minute(context):
    return
    log.info(f'============ 每分钟示例 every_minute============ cash: {context.portfolio.available_cash}')
    print_portfolio_info(context, top_n=10)

def process_initialize(context):
    return
    log.info("live_order_showcase process_initialize")
    print_portfolio_info(context, top_n=10)

def schedule_market_order(context):
    log.info(f'============ 市价单示例1（默认同步等待）  order("000001.XSHE", 100)============   cash: {context.portfolio.available_cash}')
    order("000001.XSHE", 100)
    log.info(f"============ 市价单示例1（默认同步等待） === after order cash: {context.portfolio.available_cash}")
    #print_portfolio_info(context, top_n=10)

def schedule_market_order_async(context):
    snap = get_current_data()[g.symbols["gold"]]
    last = snap.last_price or 0
    if last <= 0:
        log.warning("无法获取当前价，跳过撤单示例")
        return
    target_price = round(last * 1.02, 2)

    log.info(f'============ 市价单示例1（异步等待）  order("000001.XSHE", 100)============   cash: {context.portfolio.available_cash}')
    order(g.symbols["gold"], 200, wait_timeout=0,price=target_price)
    order(g.symbols["gold"], -100, wait_timeout=0, price=target_price)

    log.info(f"============ 市价单示例1（异步等待） === after order cash: {context.portfolio.available_cash}")
    style=MarketOrderStyle()
    order(g.symbols["gold"], -100, style=style, wait_timeout=0)
    log.info(f"============ 市价单示例1（异步等待） === after order cash: {context.portfolio.available_cash}")
    style=MarketOrderStyle(limit_price=10.0)
    order(g.symbols["gold"], 100, style=style, wait_timeout=0)
    log.info(f"============ 市价单示例1（异步等待） === after order cash: {context.portfolio.available_cash}")


def schedule_market_order_sell(context):
    log.info(f'============ 市价单示例1（默认同步等待）  order(gold, 100)============   cash: {context.portfolio.available_cash}')
    order(g.symbols["gold"], 500)
    log.info(f"============ 市价单示例1（默认同步等待）  order(gold, -100) cash: {context.portfolio.available_cash}")
    order(g.symbols["gold"], -100)
    log.info(f"============ 市价单示例1（默认同步等待） === order(gold, 500, price=target_price)  order cash: {context.portfolio.available_cash}")
    snap = get_current_data()[g.symbols["gold"]]
    last = snap.last_price or 0
    if last <= 0:
        log.warning("无法获取当前价，跳过撤单示例")
        return
    target_price = round(last * 1.01, 2)
    order(g.symbols["gold"], 100, price=target_price)
    log.info(f"============ 市价单示例1（默认同步等待）  order(gold, 500, price=target_price) cash: {context.portfolio.available_cash}")
    target_price = round(last * 0.99, 2)
    order(g.symbols["gold"], -100, price=target_price)
    log.info(f"============ 市价单示例1（默认同步等待）  === after order cash: {context.portfolio.available_cash}")

def schedule_cancel_example(context):
    """
    演示临时按市价-1% 折价生成限价单，并在随即撤单。
    """
    symbol = "000001.XSHE"
    snap = get_current_data()[symbol]
    last = snap.last_price or 0
    if last <= 0:
        log.warning("无法获取当前价，跳过撤单示例")
        return
    target_price = round(last * 0.99, 2)
    log.info(f"============ 撤单示例 下折价单，再撤销：order('{symbol}', 100, LimitOrderStyle({target_price})) ============")
    oid = order(symbol, 100, LimitOrderStyle(target_price))
    if not oid:
        log.warning("撤单示例 下单未返回 order_id，跳过撤单")
        return
    log.info(f"撤单示例 下单完成，准备撤单，order_id={oid.order_id}")
    try:
        if cancel_order(oid):
            log.info(f"撤单示例撤单成功：本地/券商已接受，order_id={oid.order_id}")
        else:
            log.warning(f"撤单示例撤单未执行（可能已成交或券商拒绝），order_id={oid.order_id}")
    except Exception as exc:
        log.error(f"撤单示例撤单失败: {exc}")
    print_portfolio_info(context, top_n=10)    

def schedule_market_order_examples(context):
    log.info(f'============ 市价单示例（默认同步等待）   order("000001.XSHE", 100)= =========== cash: {context.portfolio.available_cash}')
    order("000001.XSHE", 100)
    
    log.info(f'============ 市价单示例（默认同步等待，科创需 200 股起） order("688001.XSHG", 200, _market_style("688001.XSHG", buffer=0.01))  # 科创保护价============ cash: {context.portfolio.available_cash}')
    order("688001.XSHG", 200, _market_style("688001.XSHG", buffer=0.01))  # 科创保护价
    
    log.info(f'============ 市价单示例（默认同步等待） order("000001.XSHE", 100, LimitOrderStyle(10.0))============ cash: {context.portfolio.available_cash}')
    order("000001.XSHE", 100, MarketOrderStyle(10.0))

    log.info(f'============ 市价单示例（默认同步等待） order(g.symbols["gold"], amount=g.market_lot, style=MarketOrderStyle())============ cash: {context.portfolio.available_cash}')
    order(g.symbols["gold"], amount=g.market_lot, style=MarketOrderStyle())

    if _sell_if_available(context, g.symbols["gold"], desired=g.market_lot):
        log.info(f'============ 市价单示例（默认同步等待） after sell if available cash: {context.portfolio.available_cash}')
    else:
        log.warning(f'============ 市价单示例（默认同步等待） after sell if available cash: {context.portfolio.available_cash}')
    print_portfolio_info(context, top_n=10)


def schedule_async_market_burst(context):
    log.info("=== 异步批量下单示例（将  TRADE_MAX_WAIT_TIME=0 体验无阻塞） ===")
    buy_targets = [
        (g.symbols["gold"], g.market_lot, "黄金 ETF"),
        (g.symbols["nasdaq"], g.market_lot, "纳指 ETF"),
    ]
    for code, amount, label in buy_targets:
        log.info(f"异步买入 {label}: {code}, 数量 {amount}")
        order(code, amount=amount, style=MarketOrderStyle(), wait_timeout=0)

    sell_targets = [
        (g.symbols["pingan"], g.market_lot, "中国平安"),
        (g.symbols["cash"], g.market_lot, "银华日利"),
    ]
    for code, desired, label in sell_targets:
        if _sell_if_available(context, code, desired=desired, wait_timeout=0):
            log.info(f"异步卖出 {label}: {code}, 目标 {desired}")
        else:
            log.warning(f"{label} 当前无可卖仓位，异步卖单跳过")

    print_portfolio_info(context, top_n=10)


# def schedule_t0_roundtrip(context):
#     """覆盖 T+0 ETF 的市价/限价买卖示例（沪/深各一只）。"""
#     pairs = [
#         ("518880.XSHG", "黄金ETF（沪，T+0）"),
#         ("159949.XSHE", "创业板50ETF（深，T+0）"),
#     ]
#     for code, label in pairs:
#         log.info(f"============ T+0 示例 买入市价 {label}: order('{code}', g.market_lot) ============")
#         order(code, g.market_lot, style=MarketOrderStyle())
#         lim_price = _safe_limit_price(code, is_buy=False, buffer=0.001)
#         sold = False
#         if lim_price and _sell_if_available(context, code, desired=g.market_lot, wait_timeout=0):
#             log.info(f"============ T+0 示例 限价卖出 {label} 成功 ============")
#             sold = True
#         if not sold:
#             # 再试市价（如限价未执行则尝试）
#             order(code, amount=-g.market_lot, style=MarketOrderStyle(), wait_timeout=0)
#     print_portfolio_info(context, top_n=10)

def schedule_target_api_examples(context):
    log.info(f'============ 市价单示例（默认同步等待） order_target("000001.XSHE", 0)============ cash: {context.portfolio.available_cash}')
    order_target("000001.XSHE", 0)
    log.info(f'============ 市价单示例（默认同步等待） after order_target("000001.XSHE", 0) cash: {context.portfolio.available_cash}')
    order_target("000001.XSHE", 100)
    log.info(f'============ 市价单示例（默认同步等待，科创需 200 股起） order_target("688001.XSHG", 200, _market_style("688001.XSHG", buffer=0.01))============ cash: {context.portfolio.available_cash}')
    order_target("688001.XSHG", 200, _market_style("688001.XSHG", buffer=0.01))
    log.info(f'============ 市价单示例（默认同步等待） order_value("000001.XSHE", -10000)============ cash: {context.portfolio.available_cash}')
    order_value("000001.XSHE", -10000)
    log.info(f'============ 市价单示例（默认同步等待） order_value("000001.XSHE", 10000, MarketOrderStyle())============ cash: {context.portfolio.available_cash}')
    order_value("000001.XSHE", 10000, MarketOrderStyle())
    log.info(f'============ 市价单示例（默认同步等待） order_value("688001.XSHG", 10000, _market_style("688001.XSHG", buffer=0.01))============ cash: {context.portfolio.available_cash}')
    order_value("688001.XSHG", 10000, _market_style("688001.XSHG", buffer=0.01))
    log.info(f'============ 市价单示例（默认同步等待） order_target_value("000001.XSHE", 0)============ cash: {context.portfolio.available_cash}')
    order_target_value("000001.XSHE", 0)
    log.info(f'============ 市价单示例（默认同步等待） order_target_value("000001.XSHE", 10000)============ cash: {context.portfolio.available_cash}')
    order_target_value("000001.XSHE", 10000)
    log.info(f'============ 市价单示例（默认同步等待） order_target_value("688001.XSHG", 5000, _market_style("688001.XSHG", buffer=0.01))============ cash: {context.portfolio.available_cash}')
    order_target_value("688001.XSHG", 5000, _market_style("688001.XSHG", buffer=0.01))
    print_portfolio_info(context, top_n=10)


def schedule_limit_value_examples(context):
    log.info(f'============ 限价单示例（按价值下单） order_value(g.symbols["nasdaq"], value=4000, style=LimitOrderStyle(price))============ cash: {context.portfolio.available_cash}')
    price = _safe_limit_price(g.symbols["nasdaq"], is_buy=True, buffer=0.003)
    if price:
        order_value(g.symbols["nasdaq"], value=4000, style=LimitOrderStyle(price))
        log.info(f'============ 限价单示例（按价值下单） after order_value(g.symbols["nasdaq"], value=4000, style=LimitOrderStyle(price)) cash: {context.portfolio.available_cash}')
    else:
        log.warning(f"{g.symbols['nasdaq']} 缺少行情，跳过限价示例")

    log.info(f'============ 限价单示例（目标股数） order(g.symbols["cash"], amount=500, style=LimitOrderStyle(price_cash))============ cash: {context.portfolio.available_cash}')
    price_cash = _safe_limit_price(g.symbols["cash"], is_buy=True, buffer=0.001)
    if price_cash:
        order(g.symbols["cash"], amount=500, style=LimitOrderStyle(price_cash))
        log.info(f'============ 限价单示例（目标股数） after order(g.symbols["cash"], amount=500, style=LimitOrderStyle(price_cash)) cash: {context.portfolio.available_cash}')
    else:
        log.warning(f"{g.symbols['cash']} 缺少行情，跳过限价示例")
    log.info(f'============ 限价单示例（目标股数） after order(g.symbols["cash"], amount=500, style=LimitOrderStyle(price_cash)) cash: {context.portfolio.available_cash}')
    print_portfolio_info(context, top_n=10)


def schedule_cash_position_housekeeping(context):
    log.info(f'============ 卖出前检查可用仓位 _sell_if_available(context, g.symbols["cash"], desired=300)============ cash: {context.portfolio.available_cash}')
    if _sell_if_available(context, g.symbols["cash"], desired=300):
        log.info(f'============ 卖出前检查可用仓位 after _sell_if_available(context, g.symbols["cash"], desired=300) cash: {context.portfolio.available_cash}')
        print_portfolio_info(context, top_n=10)
    else:
        log.info(f'============ 卖出前检查可用仓位 after _sell_if_available(context, g.symbols["cash"], desired=300) cash: {context.portfolio.available_cash}')
        log.info("没有可卖的银华日利仓位，略过")


def schedule_pingan_rotation(context):
    log.info(f'============ 中国平安：目标持仓 100 股 order_target(g.symbols["pingan"], amount=100)============ cash: {context.portfolio.available_cash}')
    order_target(g.symbols["pingan"], amount=100)
    log.info(f'============ 中国平安：目标持仓 100 股 after order_target(g.symbols["pingan"], amount=100) cash: {context.portfolio.available_cash}')
    print_portfolio_info(context, top_n=10)

    log.info(f'============ 尝试 T+0 卖出 _sell_if_available(context, g.symbols["pingan"], desired=50)============ cash: {context.portfolio.available_cash}')
    if not _sell_if_available(context, g.symbols["pingan"], desired=50):
        log.info(f'============ 尝试 T+0 卖出 after _sell_if_available(context, g.symbols["pingan"], desired=50) cash: {context.portfolio.available_cash}')
        log.info("中国平安因 T+1 限制，可卖出数量不足，本轮略过")
        log.info(f'============ 尝试 T+0 卖出 after _sell_if_available(context, g.symbols["pingan"], desired=50) cash: {context.portfolio.available_cash}')
    else:
        log.info(f'============ 尝试 T+0 卖出 after _sell_if_available(context, g.symbols["pingan"], desired=50) cash: {context.portfolio.available_cash}')
        print_portfolio_info(context, top_n=10)


def _sell_if_available(context, code, desired, wait_timeout = None):
    pos = context.portfolio.positions.get(code)
    if not pos or pos.closeable_amount <= 0:
        log.info(f"{code} 当前无可卖仓位")
        return False
    amount = min(int(pos.closeable_amount), desired)
    if amount <= 0:
        log.info(f"{code} 可卖数量不足，跳过")
        return False
    price = _safe_limit_price(code, is_buy=False, buffer=0.002)
    if not price:
        log.warning(f"{code} 缺少行情，无法卖出")
        return False
    order(code, amount=-amount, price=price, wait_timeout=wait_timeout)
    return True


def _market_style(code, buffer):
    price = _safe_limit_price(code, is_buy=True, buffer=buffer)
    if price:
        return MarketOrderStyle(price)
    log.warning(f"{code} 缺少行情，使用默认市价单")
    return MarketOrderStyle()


def _safe_limit_price(code, is_buy, buffer):
    current_data = get_current_data()
    try:
        snapshot = current_data[code]
    except Exception:
        log.warning(f"{code} 当前缺少行情数据")
        return None

    last = float(snapshot.last_price or snapshot.high_limit or snapshot.low_limit or 0)
    if last <= 0:
        log.warning(f"{code} 缺少有效价格")
        return None

    candidate = last * (1 + buffer if is_buy else 1 - buffer)
    if is_buy and snapshot.high_limit:
        candidate = min(candidate, float(snapshot.high_limit) * 0.999)
    if not is_buy and snapshot.low_limit:
        candidate = max(candidate, float(snapshot.low_limit) * 1.001)

    tick = _infer_min_price_step(code, candidate)
    candidate = round(candidate / tick) * tick

    if is_buy and snapshot.high_limit:
        candidate = min(candidate, float(snapshot.high_limit))
    if not is_buy and snapshot.low_limit:
        candidate = max(candidate, float(snapshot.low_limit))
    return max(candidate, tick)


def _infer_min_price_step(code, price):
    market = code.split(".")[-1].upper()
    core = code.split(".")[0]
    if (market in ("XSHG", "SH") and core.startswith("5")) or (
        market in ("XSHE", "SZ") and core.startswith("1")
    ):
        return 0.001
    if price < 1:
        return 0.001
    return 0.01
