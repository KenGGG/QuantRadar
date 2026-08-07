"""
演示按名称直接访问 provider 特有接口：
- 默认数据源使用 QMT，对照 JQData 价格
- 直接调用 JQData 特有/原生接口获取指数成分与市值 Top 10
"""
from datetime import date as Date
import os

import pandas as pd
import pytest

from jqdata import *  # noqa: F401,F403

from bullet_trade.data.api import get_data_provider, get_price, set_data_provider
from bullet_trade.utils.env_loader import load_env
from bullet_trade.utils.strategy_helpers import prettytable_print_df


def _require_env():
    load_env()
    jq_user = os.environ.get("JQDATA_USERNAME") or os.environ.get("JQDATA_USER")
    jq_pwd = os.environ.get("JQDATA_PASSWORD") or os.environ.get("JQDATA_PWD")
    if not jq_user or not jq_pwd:
        pytest.skip("缺少 JQDATA_USERNAME/JQDATA_PASSWORD，跳过直连示例")
    try:
        import jqdatasdk  # noqa: F401
    except Exception as exc:  # pragma: no cover - 依赖缺失才触发
        pytest.skip(f"未安装 jqdatasdk，跳过直连示例: {exc}")
    try:
        from xtquant import xtdata  # noqa: F401
    except Exception as exc:  # pragma: no cover - 依赖缺失才触发
        pytest.skip(f"缺少 miniQMT/xtquant 环境，跳过直连示例: {exc}")


def initialize(context):
    _require_env()
    # 默认用 QMT，后续单独取 JQData 实例对照
    set_data_provider("qmt")
    g.trade_date = Date(2025, 11, 25)
    g.index_code = "399101.XSHE"


def before_trading_start(context):
    jq_provider = get_data_provider("jqdata")

    # 先用 JQData 取指数成分，作为对照列表
    try:
        components = jq_provider.get_index_stocks(g.index_code, date=g.trade_date)
    except Exception as exc:
        pytest.skip(f"获取 {g.index_code} 成分失败，跳过：{exc}")
    if not components:
        pytest.skip(f"{g.index_code} 成分为空，跳过示例")

    target = components[0]

    # 默认数据源（QMT）与 JQData 的价格对照
    try:
        default_price_df = get_price(
            target,
            end_date=g.trade_date,
            frequency="daily",
            fields=["close"],
            count=1,
            fq=None,
        )
        default_price = float(default_price_df["close"].iloc[-1])
    except Exception as exc:
        pytest.skip(f"默认数据源无法获取 {target} 价格：{exc}")

    try:
        jq_price_df = jq_provider.get_price(
            target,
            end_date=g.trade_date,
            frequency="daily",
            fields=["close"],
            count=1,
            fq=None,
        )
        jq_price = float(jq_price_df["close"].iloc[-1])
    except Exception as exc:
        pytest.skip(f"JQData 无法获取 {target} 价格：{exc}")

    log.info("[直连对照] %s 默认源价格=%.4f, jqdata=%.4f", target, default_price, jq_price)

    # 获取市值最小的前10个成分（JQData 特有接口）
    try:
        import jqdatasdk as jq

        q = (
            jq.query(
                jq.valuation.code,
                jq.valuation.display_name,
                jq.valuation.market_cap,
            )
            .filter(jq.valuation.code.in_(components))
            .order_by(jq.valuation.market_cap.asc())
            .limit(10)
        )
        df = jq_provider.get_fundamentals(q, date=g.trade_date)
        df = df.rename(columns={"code": "证券代码", "display_name": "名称", "market_cap": "市值(亿)"})
        df["市值(亿)"] = pd.to_numeric(df["市值(亿)"], errors="coerce")
        df = df.sort_values("市值(亿)").reset_index(drop=True)
        prettytable_print_df(df.head(10))
    except Exception as exc:
        pytest.skip(f"JQData 基础数据不可用，跳过市值对照：{exc}")


def handle_data(context, data):
    # 本示例只做单次对照
    pass
