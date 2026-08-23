from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import AuditStatus, GateEvidence


_REQUIRED_EVIDENCE = (
    "price_semantics",
    "corporate_action",
    "pit_universe",
    "latest_tradeability",
)


def derive_latest_tradeability_evidence(
    coverage_rows: list[dict[str, Any]],
) -> GateEvidence:
    by_dataset = {str(row["dataset"]): row for row in coverage_rows}
    price_date = by_dataset.get("price", {}).get("max_date")
    required = (
        "index_constituents",
        "up_down_limits",
        "st",
        "tradestatus_paused",
        "corporate_action_proxy",
        "stock_master",
    )
    missing = [name for name in required if by_dataset.get(name, {}).get("max_date") is None]
    if price_date is None or missing:
        details = ", ".join(missing) if missing else "price"
        return GateEvidence.blocked(
            f"Missing latest coverage for: {details}", "coverage.csv"
        )
    stale = [
        f"{name}={by_dataset[name]['max_date']} < price={price_date}"
        for name in required
        if by_dataset[name]["max_date"] < price_date
    ]
    if stale:
        return GateEvidence.partial("; ".join(stale), "coverage.csv")
    return GateEvidence.pass_("coverage.csv")


def derive_pit_universe_evidence(
    checked: GateEvidence,
    coverage_rows: list[dict[str, Any]],
) -> GateEvidence:
    if not checked.ready:
        return checked
    by_dataset = {str(row["dataset"]): row for row in coverage_rows}
    index = by_dataset.get("index_constituents", {})
    price = by_dataset.get("price", {})
    first = index.get("min_date")
    last = index.get("max_date")
    latest_price = price.get("max_date")
    if first is None or last is None or latest_price is None:
        return GateEvidence.blocked(
            "PIT index or price coverage boundary is missing",
            "pit_universe_checks.csv",
            "coverage.csv",
        )
    required_start = first.replace(year=2015, month=1, day=1)
    reasons = []
    if first > required_start:
        reasons.append(f"000300.SH starts at {first}, later than required {required_start}")
    if last < latest_price:
        reasons.append(f"000300.SH ends at {last}, earlier than latest price {latest_price}")
    if reasons:
        return GateEvidence.partial(
            "; ".join(reasons),
            "pit_universe_checks.csv",
            "coverage.csv",
        )
    return checked


def derive_data_gates(evidence: Mapping[str, GateEvidence]) -> dict[str, Any]:
    """从 4 项底层证据推导能力分层门禁。

    模型（已对代码逐条核实：``signal_ready = price_ready and pit_ready`` 是
    QuantRadar 自定义的严格 CSI300 研究要求，并非 Kronos 要求）：

        price_data_ready            = price_semantics.ready                         # True
        kronos_input_ready          = price_data_ready                              # OHLC(+VA) 满足 Kronos
        kronos_signal_research_ready= kronos_input_ready and universe_default_ready # True
        csi300_pit_ready            = pit_universe.ready                            # 独立能力（PARTIAL）
        realistic_backtest_ready    = kronos_signal_research_ready
                                   and latest_tradeability.status != BLOCKED       # True；fidelity=PARTIAL
        real_assist_data_ready      = kronos_signal_research_ready
                                   and latest_tradeability.status == PASS          # False（当前 stale）

    ``universe_default_ready`` 恒为 True：默认宇宙 ``all_a_liquid`` 仅依赖持续更新
    的行情数据即可构造，不依赖任何 PIT 成分快照。一个指数 PIT 能力缺失（
    ``csi300_pit_ready`` 为 False/PARTIAL）不会阻塞 Kronos 信号研究。
    """
    missing = [name for name in _REQUIRED_EVIDENCE if name not in evidence]
    if missing:
        raise ValueError(f"missing gate evidence: {', '.join(missing)}")

    price_ready = evidence["price_semantics"].ready
    action_ready = evidence["corporate_action"].ready
    pit_ready = evidence["pit_universe"].ready
    tradeability = evidence["latest_tradeability"]
    tradeability_ready = tradeability.ready
    tradeability_status = tradeability.status

    universe_default_ready = True  # all_a_liquid 仅依赖价格，恒 True

    price_data_ready = price_ready
    kronos_input_ready = price_data_ready
    kronos_signal_research_ready = kronos_input_ready and universe_default_ready
    research_backtest_ready = kronos_signal_research_ready
    csi300_pit_ready = pit_ready  # 独立能力，不作为全局阻塞
    realistic_backtest_ready = (
        research_backtest_ready
        and tradeability_status != AuditStatus.BLOCKED
    )
    formal_backtest_ready = (
        research_backtest_ready
        and action_ready
        and tradeability_status == AuditStatus.PASS
    )
    real_assist_data_ready = (
        kronos_signal_research_ready
        and tradeability_status == AuditStatus.PASS
    )

    # csi300_pit_ready 的 fidelity 以底层 PIT 证据状态为准（PASS/PARTIAL/BLOCKED）。
    csi300_pit_fidelity = evidence["pit_universe"].status.value
    fidelity = {
        "kronos_input_ready": "PASS" if kronos_input_ready else "BLOCKED",
        "kronos_signal_research_ready": (
            "PASS" if kronos_signal_research_ready else "BLOCKED"
        ),
        "research_backtest_ready": "PASS" if research_backtest_ready else "BLOCKED",
        "csi300_pit_ready": csi300_pit_fidelity,
        "realistic_backtest_ready": "PARTIAL" if realistic_backtest_ready else "BLOCKED",
        "formal_backtest_ready": "PASS" if formal_backtest_ready else "BLOCKED",
        "real_assist_data_ready": "PASS" if real_assist_data_ready else "BLOCKED",
    }

    return {
        "price_semantics_ready": price_ready,
        "corporate_action_ready": action_ready,
        "pit_universe_ready": pit_ready,
        "latest_tradeability_ready": tradeability_ready,
        # 新 4 层能力门禁
        "price_data_ready": price_data_ready,
        "kronos_input_ready": kronos_input_ready,
        "kronos_signal_research_ready": kronos_signal_research_ready,
        "research_backtest_ready": research_backtest_ready,
        "csi300_pit_ready": csi300_pit_ready,
        "realistic_backtest_ready": realistic_backtest_ready,
        "real_assist_data_ready": real_assist_data_ready,
        # 向后兼容别名（平滑过渡，后续 Goal 清理）
        "signal_research_ready": kronos_signal_research_ready,
        "formal_backtest_ready": formal_backtest_ready,
        "fidelity": fidelity,
        "gates": {name: evidence[name].as_dict() for name in _REQUIRED_EVIDENCE},
    }
