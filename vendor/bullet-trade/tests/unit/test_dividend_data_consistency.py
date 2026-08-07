"""
分红数据一致性测试：验证不同 provider 返回的分红事件数据格式与数值完全一致。

测试目标：
1. 确保 JQData、MiniQMT、Tushare 三个数据源的 get_split_dividend 返回相同的分红数据
2. 验证 per_base 和 bonus_pre_tax 字段的正确性
3. 股票：per_base=10, bonus_pre_tax 为每10股派息
4. 基金：per_base=1, bonus_pre_tax 为每1份派息
"""

import os
from datetime import date as Date
from typing import Dict, List, Any, Optional

import pytest


# 黄金标准：基于聚宽官方数据的正确分红事件
GOLDEN_DIVIDENDS: Dict[str, List[Dict[str, Any]]] = {
    "601318.XSHG": [
        {
            "security": "601318.XSHG",
            "date": Date(2024, 7, 26),
            "security_type": "stock",
            "per_base": 10,
            "bonus_pre_tax": 15.0,  # 每10股派15元
            "scale_factor": 1.0,
        },
        {
            "security": "601318.XSHG",
            "date": Date(2024, 10, 18),
            "security_type": "stock",
            "per_base": 10,
            "bonus_pre_tax": 9.3,  # 每10股派9.3元
            "scale_factor": 1.0,
        },
    ],
    "511880.XSHG": [
        {
            "security": "511880.XSHG",
            "date": Date(2024, 12, 31),
            "security_type": "fund",
            "per_base": 1,
            "bonus_pre_tax": 1.5521,  # 每1份派1.5521元
            "scale_factor": 1.0,
        }
    ],
}


def _get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """获取环境变量，兼容 env_loader"""
    try:
        from bullet_trade.utils.env_loader import get_env
        return get_env(key, default)
    except Exception:
        return os.environ.get(key, default)


def _normalize_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """标准化事件字段，方便对比"""
    return {
        "security": event.get("security"),
        "date": event.get("date"),
        "security_type": event.get("security_type"),
        "per_base": float(event.get("per_base", 0)),
        "bonus_pre_tax": round(float(event.get("bonus_pre_tax", 0)), 4),
        "scale_factor": round(float(event.get("scale_factor", 1.0)), 6),
    }


def _fetch_dividends_from_provider(
    provider_name: str, security: str, start_date: Date, end_date: Date
) -> List[Dict[str, Any]]:
    """从指定 provider 获取分红数据"""
    from bullet_trade.data import set_data_provider, get_data_provider
    from bullet_trade.data.api import _provider as original_provider

    # 临时切换 provider
    try:
        set_data_provider(provider_name)
        provider = get_data_provider()
        events = provider.get_split_dividend(security, start_date=start_date, end_date=end_date)
        return [_normalize_event(e) for e in events]
    finally:
        # 恢复原 provider
        from bullet_trade.data import api
        api._provider = original_provider
        api._auth_attempted = False


@pytest.mark.unit
def test_golden_dividends_format():
    """验证黄金标准数据格式正确性"""
    # 验证股票分红
    stock_events = GOLDEN_DIVIDENDS["601318.XSHG"]
    assert len(stock_events) == 2
    for event in stock_events:
        assert event["per_base"] == 10, "股票分红 per_base 应为 10"
        assert event["bonus_pre_tax"] > 0, "bonus_pre_tax 应大于 0"
        assert event["security_type"] == "stock"

    # 验证基金分红
    fund_events = GOLDEN_DIVIDENDS["511880.XSHG"]
    assert len(fund_events) == 1
    event = fund_events[0]
    assert event["per_base"] == 1, "基金分红 per_base 应为 1"
    assert event["bonus_pre_tax"] == 1.5521
    assert event["security_type"] == "fund"


@pytest.mark.requires_network
def test_provider_dividends_match_golden(provider_name: str):
    """
    验证各 provider 的分红数据与黄金标准一致。
    
    测试用例：
    1. 601318.XSHG (中国平安) - 2024-07-26: 每10股派15元
    2. 601318.XSHG (中国平安) - 2024-10-18: 每10股派9.3元
    3. 511880.XSHG (银华日利ETF) - 2024-12-31: 每1份派1.5521元
    """
    # 环境检查
    if provider_name == "jqdata":
        if not (_get_env("JQDATA_USERNAME") and _get_env("JQDATA_PASSWORD")):
            pytest.skip("缺少 JQDATA_USERNAME/JQDATA_PASSWORD")
        try:
            import jqdatasdk  # noqa: F401
        except ImportError:
            pytest.skip("未安装 jqdatasdk")
    elif provider_name == "miniqmt":
        if not _get_env("QMT_DATA_PATH"):
            pytest.skip("缺少 QMT_DATA_PATH")
        try:
            import xtquant  # noqa: F401
        except ImportError:
            pytest.skip("未安装 xtquant")
    elif provider_name == "tushare":
        if not _get_env("TUSHARE_TOKEN"):
            pytest.skip("缺少 TUSHARE_TOKEN")
        try:
            import tushare  # noqa: F401
        except ImportError:
            pytest.skip("未安装 tushare")

    # 测试每个证券的分红数据
    for security, golden_events in GOLDEN_DIVIDENDS.items():
        if not golden_events:
            continue

        # 确定查询时间范围
        dates = [e["date"] for e in golden_events]
        start_date = min(dates)
        end_date = max(dates)

        # 获取 provider 数据
        try:
            provider_events = _fetch_dividends_from_provider(
                provider_name, security, start_date, end_date
            )
        except Exception as exc:
            pytest.fail(f"{provider_name} 获取 {security} 分红数据失败: {exc}")

        # 验证事件数量
        assert len(provider_events) == len(
            golden_events
        ), f"{provider_name} 返回的 {security} 分红事件数量不匹配: 期望 {len(golden_events)}, 实际 {len(provider_events)}"

        # 按日期排序
        provider_events = sorted(provider_events, key=lambda x: x["date"])
        golden_events_sorted = sorted(golden_events, key=lambda x: x["date"])

        # 逐个对比
        for i, (golden, provider) in enumerate(zip(golden_events_sorted, provider_events)):
            event_desc = f"{security} 第{i+1}个分红事件 ({golden['date']})"

            # 关键字段必须完全一致
            assert provider["date"] == golden["date"], f"{provider_name} {event_desc} 日期不匹配"

            assert (
                provider["per_base"] == golden["per_base"]
            ), f"{provider_name} {event_desc} per_base 不匹配: 期望 {golden['per_base']}, 实际 {provider['per_base']}"

            # bonus_pre_tax 允许小数点后4位误差
            golden_bonus = golden["bonus_pre_tax"]
            provider_bonus = provider["bonus_pre_tax"]
            assert abs(provider_bonus - golden_bonus) < 0.0001, (
                f"{provider_name} {event_desc} bonus_pre_tax 不匹配: "
                f"期望 {golden_bonus}, 实际 {provider_bonus}"
            )

            assert (
                provider["security_type"] == golden["security_type"]
            ), f"{provider_name} {event_desc} security_type 不匹配"


@pytest.mark.requires_network
def test_cross_provider_consistency():
    """
    交叉验证：确保 jqdata、miniqmt、tushare 返回完全相同的分红数据。
    
    这个测试会同时查询多个 provider，确保它们返回的数据一致。
    """
    available_providers = []

    # 检查哪些 provider 可用
    if _get_env("JQDATA_USERNAME") and _get_env("JQDATA_PASSWORD"):
        try:
            import jqdatasdk  # noqa: F401
            available_providers.append("jqdata")
        except ImportError:
            pass

    if _get_env("QMT_DATA_PATH"):
        try:
            import xtquant  # noqa: F401
            available_providers.append("miniqmt")
        except ImportError:
            pass

    if _get_env("TUSHARE_TOKEN"):
        try:
            import tushare  # noqa: F401
            available_providers.append("tushare")
        except ImportError:
            pass

    if len(available_providers) < 2:
        pytest.skip(f"至少需要2个可用的 provider，当前只有 {len(available_providers)} 个")

    # 对每个证券，比较所有可用 provider 的数据
    for security, golden_events in GOLDEN_DIVIDENDS.items():
        if not golden_events:
            continue

        dates = [e["date"] for e in golden_events]
        start_date = min(dates)
        end_date = max(dates)

        # 获取所有 provider 的数据
        all_provider_events: Dict[str, List[Dict[str, Any]]] = {}
        for provider_name in available_providers:
            try:
                events = _fetch_dividends_from_provider(
                    provider_name, security, start_date, end_date
                )
                all_provider_events[provider_name] = sorted(events, key=lambda x: x["date"])
            except Exception as exc:
                pytest.fail(f"{provider_name} 获取 {security} 数据失败: {exc}")

        # 交叉对比：每两个 provider 之间的数据应该一致
        provider_list = list(all_provider_events.keys())
        for i in range(len(provider_list)):
            for j in range(i + 1, len(provider_list)):
                provider1 = provider_list[i]
                provider2 = provider_list[j]
                events1 = all_provider_events[provider1]
                events2 = all_provider_events[provider2]

                assert len(events1) == len(events2), (
                    f"{security}: {provider1} 和 {provider2} 返回的事件数量不一致: "
                    f"{len(events1)} vs {len(events2)}"
                )

                for k, (e1, e2) in enumerate(zip(events1, events2)):
                    event_desc = f"{security} 第{k+1}个事件"

                    assert e1["date"] == e2["date"], f"{event_desc} 日期不一致: {provider1}={e1['date']}, {provider2}={e2['date']}"

                    assert e1["per_base"] == e2["per_base"], (
                        f"{event_desc} per_base 不一致: "
                        f"{provider1}={e1['per_base']}, {provider2}={e2['per_base']}"
                    )

                    assert abs(e1["bonus_pre_tax"] - e2["bonus_pre_tax"]) < 0.0001, (
                        f"{event_desc} bonus_pre_tax 不一致: "
                        f"{provider1}={e1['bonus_pre_tax']}, {provider2}={e2['bonus_pre_tax']}"
                    )


@pytest.mark.requires_network
def test_dividend_cash_calculation():
    """
    验证分红现金计算的正确性。
    
    根据持仓数量和分红数据，计算实际入账现金是否正确。
    测试场景：持有 1200 股 601318.XSHG，税率 20%
    """
    # 601318.XSHG 第一次分红：2024-07-26, 每10股派15元
    per_base = 10
    bonus_pre_tax = 15.0
    holding = 1200
    tax_rate = 0.20

    # 计算现金入账
    cash_in = (holding / per_base) * bonus_pre_tax * (1 - tax_rate)

    # 期望值：(1200/10) * 15 * 0.8 = 1440.00
    expected_cash = 1440.00
    assert abs(cash_in - expected_cash) < 0.01, (
        f"601318.XSHG 分红现金计算错误: 期望 {expected_cash}, 实际 {cash_in}"
    )

    # 511880.XSHG 分红：2024-12-31, 每1份派1.5521元，货币基金免税
    per_base = 1
    bonus_pre_tax = 1.5521
    holding = 400
    tax_rate = 0.0

    cash_in = (holding / per_base) * bonus_pre_tax * (1 - tax_rate)

    # 期望值：(400/1) * 1.5521 * 1.0 = 620.84
    expected_cash = 620.84
    assert abs(cash_in - expected_cash) < 0.01, (
        f"511880.XSHG 分红现金计算错误: 期望 {expected_cash}, 实际 {cash_in}"
    )


if __name__ == "__main__":
    # 支持直接运行此文件进行快速测试
    pytest.main([__file__, "-v", "-s"])

