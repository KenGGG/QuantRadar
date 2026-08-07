"""Closing Phase 1：完整 Snapshot / Audit 与可复现验证（FULL_AUDIT_REPRO_PASS）。

验证 build_snapshot 补齐审计字段，且同配置两次运行：
    - NAV 一致（daily_records total_value 序列）
    - Trades 一致（成交指纹）
    - Positions 一致（持仓指纹）
    - Metrics 一致（收益/回撤/天数）
    - 审计指纹一致（config_hash / strategy_hash / result_hash / dolt_commit / schema_hash）
真实数据，无 mock。
"""

from __future__ import annotations

from bullet_trade.core.engine import BacktestEngine

from quantradar.bootstrap import bootstrap_investment_data
from quantradar.snapshot import build_snapshot

SECURITY = "600519.XSHG"
START = "2023-01-01"
END = "2023-03-31"
CASH = 500000


def _buy_hold_strategy():
    def initialize(context):  # noqa: ANN001
        context.security = SECURITY
        context.amount = 100

    def handle_data(context, data):  # noqa: ANN001
        if not context.portfolio.positions:
            order_target(context.security, context.amount)

    return initialize, handle_data


def _run_once(strategy_source: str | None = None):
    init, hd = _buy_hold_strategy()
    engine = BacktestEngine(
        initialize=init,
        handle_data=hd,
        start_date=START,
        end_date=END,
        frequency="day",
        initial_cash=CASH,
    )
    engine.run()
    nav = [round(r.get("total_value"), 6) for r in engine.daily_records if r.get("total_value") is not None]
    snap = build_snapshot(engine, strategy_source=strategy_source)
    return snap, nav


def test_snapshot_has_full_audit_fields():
    bootstrap_investment_data(set_active=True, overwrite=True)
    snap, _ = _run_once()
    assert "snapshot_id" in snap and isinstance(snap["snapshot_id"], str) and len(snap["snapshot_id"]) > 0
    assert "config_hash" in snap and snap["config_hash"]
    assert "strategy_hash" in snap and snap["strategy_hash"]
    assert "result_hash" in snap and snap["result_hash"]
    assert "metrics" in snap and snap["metrics"]
    env = snap["environment"]
    for key in ("provider", "provider_version", "dolt_commit", "schema_hash",
                "bullettrade_commit", "quantradar_commit"):
        assert key in env, f"审计字段缺失：{key}"
        assert env[key] not in (None, "", "unknown"), f"审计字段未填充：{key}={env[key]}"


def test_deterministic_nav_trades_positions_metrics():
    bootstrap_investment_data(set_active=True, overwrite=True)
    (s1, nav1), (s2, nav2) = _run_once(), _run_once()

    # NAV 一致
    assert nav1 == nav2 and len(nav1) > 0
    # Trades / Positions / Metrics 一致（结果哈希已覆盖）
    assert s1["result_hash"] == s2["result_hash"]
    assert s1["metrics"] == s2["metrics"]
    # 审计指纹一致
    assert s1["config_hash"] == s2["config_hash"]
    assert s1["strategy_hash"] == s2["strategy_hash"]
    assert s1["environment"]["dolt_commit"] == s2["environment"]["dolt_commit"]
    assert s1["environment"]["schema_hash"] == s2["environment"]["schema_hash"]
    # 确定性指标本身合理
    assert s1["metrics"]["days"] == len(nav1)
    assert s1["metrics"]["final_total_value"] == nav1[-1]


def test_user_strategy_source_changes_strategy_hash():
    bootstrap_investment_data(set_active=True, overwrite=True)
    a = _run_once(strategy_source="def handle_data(context, data):\n    pass\n")
    b = _run_once(strategy_source="def handle_data(context, data):\n    order_target('600519.XSHG', 100)\n")
    # 不同源码 -> 不同策略哈希；同配置下 config_hash 一致
    assert a[0]["strategy_hash"] != b[0]["strategy_hash"]
    assert a[0]["config_hash"] == b[0]["config_hash"]
