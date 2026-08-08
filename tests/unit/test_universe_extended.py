"""T2 股票列表补全（Point-in-Time 宇宙近似）单元测试。

覆盖链路：investment_data(Dolt) → extended_universe（从 final 价格表补全 ts_a_stock_list
缺口）→ select_universe(use_extended=True) 合并入 Qlib 宇宙。

环境约束：
    - 需要可达的 investment_data（Dolt @127.0.0.1:3307）；不可达则经 requires_dolt 自动 skip。
    - 不依赖 qlib/lightgbm（仅校验宇宙补全与 PIT 正确），故比 Qlib 闭环测试更轻。
    - 绝不伪造：补全来源统一标注 source='final_approx'（PARTIAL），由研究层谨慎使用。
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.requires_dolt

from quantradar.providers.investment_data.provider import extended_universe
from quantradar.providers.investment_data.symbols import to_ts_symbol
from quantradar.qml.dump import select_universe


def test_extended_universe_source_and_pit(db_connection):
    """extended_universe 返回的记录应：来源 final_approx、窗口起点前已上市、不在 ts 列表中。"""
    start, end = "2024-01-01", "2024-12-31"
    recs = extended_universe(db_connection, start, end, max_instruments=200)
    assert recs, "应补全出 ts_a_stock_list 缺口（2022-07-18 后）上市股"

    known_ts = {r["ts_code"] for r in db_connection.query("SELECT ts_code FROM ts_a_stock_list")}

    for rec in recs:
        # 1) 来源标注明确（PARTIAL，绝不冒充实权威列表）
        assert rec["source"] == "final_approx"
        # 2) Point-in-Time：近似 list_date 必须 <= 窗口起点（窗口起点已上市）
        assert rec["list_date"] <= start, f"{rec['jq']} 首现日 {rec['list_date']} 晚于窗口起点 {start}"
        # 3) 确属 ts 列表缺口（不在权威列表中）
        assert rec["ts_code"] not in known_ts, f"{rec['ts_code']} 竟在 ts_a_stock_list 中"
        # 4) 代码可解析为 ts 风格
        assert to_ts_symbol(rec["jq"]) == rec["ts_code"]


def test_select_universe_extended_is_superset(db_connection):
    """use_extended=True 应将补全标的并入宇宙（合并后确定性排序取前 N 只）。

    合并语义下不保证 base ⊆ ext（cap 较小会截断合并结果），但应保证：
    - ext 与 base 组合不同（纳入了补全标的）；
    - 新增标的（ext - base）非空且全部来自 final_approx（不在 ts 列表中）。
    """
    start, end = "2024-01-01", "2024-12-31"
    base = select_universe(db_connection, start, end, max_instruments=300, use_extended=False)
    ext = select_universe(db_connection, start, end, max_instruments=300, use_extended=True)

    assert base, "基础宇宙不应为空"
    assert len(ext) <= 300
    assert set(ext) != set(base), "扩展宇宙应与基础宇宙组合不同（应纳入补全标的）"
    added = set(ext) - set(base)
    assert added, "扩展宇宙应至少补全一只 ts 列表缺口股"
    # 新增标的全部来自 final_approx（即不在 ts 列表中，且非指数）
    known_ts = {r["ts_code"] for r in db_connection.query("SELECT ts_code FROM ts_a_stock_list")}
    index_codes = {
        r["index_code"] for r in db_connection.query("SELECT DISTINCT index_code FROM ts_index_weight")
    }
    for jq in added:
        ts = to_ts_symbol(jq)
        assert ts not in known_ts, f"{jq} 竟在 ts_a_stock_list 中（不应作为补全标的）"
        assert ts not in index_codes, f"{jq} 是指数代码，不应作为补全标的"


def test_extended_universe_deterministic(db_connection):
    """同一输入两次调用结果应完全一致（确定性排序，无随机抽样）。"""
    start, end = "2024-01-01", "2024-12-31"
    a = extended_universe(db_connection, start, end, max_instruments=200)
    b = extended_universe(db_connection, start, end, max_instruments=200)
    assert [r["jq"] for r in a] == [r["jq"] for r in b]
    assert [r["source"] for r in a] == [r["source"] for r in b]
