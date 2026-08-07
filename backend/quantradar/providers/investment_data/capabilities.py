"""InvestmentDataProvider 能力矩阵（统一状态标记）。

状态取值（见 docs/00 与 docs/03）：
    PASS        能力完整、数据齐备、测试通过
    PARTIAL     能力可用但有已知限制（记录限制范围）
    LIMIT       仅部分市场/字段可用
    UNSUPPORTED 当前架构明确不支持（记录原因）
    BLOCKED     数据缺失或依赖未就绪，不可使用
    FAIL        已实现但测试不通过

本矩阵为「声明式事实」，由单元测试与真实查询支撑；不得凭 README 猜测。
"""

from __future__ import annotations

from typing import Dict

# Phase 2A 时点能力状态
CAPABILITIES: Dict[str, Dict[str, str]] = {
    "connection": {
        "status": "PASS",
        "note": "只读 pymysql 连接（3307），超时/探针/明确错误齐备",
    },
    "symbol_mapping": {
        "status": "PASS",
        "note": "股票/指数多格式集中归一化，非法输入抛 SymbolError",
    },
    "get_trade_days": {
        "status": "PASS",
        "note": "ts_trade_day_calendar（SSE, is_open=1），支持 start/end/count",
    },
    "get_all_securities": {
        "status": "PARTIAL",
        "note": "ts_a_stock_list 提供 ts_code/symbol/exchange/list_date/delist_date；"
        "该源无 display_name/name 列 -> name 不可用（LIMIT）；当前仅 stock 类型",
    },
    "get_security_info": {
        "status": "PARTIAL",
        "note": "同 get_all_securities 来源；name 不可用",
    },
    "get_index_stocks": {
        "status": "PASS",
        "note": "ts_index_weight，按指定 date 取最近交易日快照（PIT），返回 JoinQuant 代码",
    },
    "get_index_weights": {
        "status": "PASS",
        "note": "ts_index_weight，按指定 date 取最近交易日快照（PIT）",
    },
    "get_price": {
        "status": "UNSUPPORTED",
        "note": "日频原始价见 Phase 2B（final_a_stock_eod_price）",
    },
    "get_split_dividend": {
        "status": "UNSUPPORTED",
        "note": "公司行为红利/拆股见 Phase 5",
    },
    "etf": {
        "status": "BLOCKED",
        "note": "investment_data 无 ETF 表；Phase 11 前不建设（不阻塞股票主线）",
    },
}


def capability_summary() -> str:
    """返回可读的能力清单（用于数据页/日志）。"""
    lines = []
    for name, info in CAPABILITIES.items():
        lines.append(f"  {name:22s} {info['status']:12s} {info['note']}")
    return "\n".join(lines)
