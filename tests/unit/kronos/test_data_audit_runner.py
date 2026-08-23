from __future__ import annotations

import datetime as dt
import json

import pytest

from quantradar.kronos.data_audit.models import GateEvidence
from quantradar.kronos.data_audit.runner import DataVersionChangedError, run_data_audit


class HeadConnection:
    def __init__(self, heads: list[str]):
        self.heads = list(heads)

    def query_one(self, sql, args=None):
        assert "dolt_log" in sql
        return {"commit_hash": self.heads.pop(0)}


def audit_bundle():
    return {
        "schema": {
            "schemas": {"final_a_stock_eod_price": [{"name": "tradedate", "type": "date"}]},
            "table_summaries": [],
            "coverage": [
                {
                    "dataset": "price",
                    "table": "final_a_stock_eod_price",
                    "date_column": "tradedate",
                    "min_date": dt.date(1990, 12, 19),
                    "max_date": dt.date(2026, 8, 18),
                    "row_count": 18_000_000,
                },
                {
                    "dataset": "st",
                    "table": "bao_a_stock_eod_info",
                    "date_column": "tradedate",
                    "min_date": dt.date(1990, 12, 19),
                    "max_date": dt.date(2023, 6, 9),
                    "row_count": 14_000_000,
                },
                {
                    "dataset": "index_constituents",
                    "table": "ts_index_weight",
                    "date_column": "trade_date",
                    "min_date": dt.date(2020, 1, 2),
                    "max_date": dt.date(2022, 7, 1),
                    "row_count": 18_300,
                },
                {
                    "dataset": "up_down_limits",
                    "table": "final_a_stock_limit",
                    "date_column": "tradedate",
                    "min_date": dt.date(1990, 12, 19),
                    "max_date": dt.date(2023, 6, 9),
                    "row_count": 12_000_000,
                },
                {
                    "dataset": "tradestatus_paused",
                    "table": "bao_a_stock_eod_info",
                    "date_column": "tradedate",
                    "min_date": dt.date(1990, 12, 19),
                    "max_date": dt.date(2023, 6, 9),
                    "row_count": 14_000_000,
                },
                {
                    "dataset": "corporate_action_proxy",
                    "table": "bao_a_stock_eod_info",
                    "date_column": "tradedate",
                    "min_date": dt.date(1990, 12, 19),
                    "max_date": dt.date(2023, 6, 9),
                    "row_count": 14_000_000,
                },
                {
                    "dataset": "stock_master",
                    "table": "ts_a_stock_list",
                    "date_column": "list_date",
                    "min_date": dt.date(1990, 12, 19),
                    "max_date": dt.date(2023, 6, 9),
                    "row_count": 5_200,
                },
            ],
        },
        "prices": {
            "rows": [{"symbol": "600519.XSHG", "status": "PASS"}],
            "contract": {"raw_price": "final_a_stock_eod_price OHLC"},
            "evidence": GateEvidence.pass_("price_semantics.csv"),
        },
        "actions": {
            "rows": [{"symbol": "SH600519", "status": "PARTIAL"}],
            "evidence": GateEvidence.partial("No event fact table", "corporate_actions.csv"),
        },
        "universe": {
            "rows": [{"audit_date": dt.date(2022, 6, 24), "status": "PASS"}],
            "evidence": GateEvidence.pass_("pit_universe_checks.csv"),
        },
    }


def test_run_data_audit_publishes_required_files_with_json_safe_dates(tmp_path):
    output = tmp_path / "audit"

    result = run_data_audit(
        HeadConnection(["abc123", "abc123"]),
        provider=object(),
        output_dir=output,
        collect_fn=lambda connection, provider: audit_bundle(),
        generated_at=dt.datetime(2026, 8, 21, 10, 0, tzinfo=dt.timezone.utc),
    )

    assert {path.name for path in output.iterdir()} == {
        "audit_manifest.json",
        "corporate_actions.csv",
        "coverage.csv",
        "data_contract.json",
        "data_gate.json",
        "pit_universe_checks.csv",
        "price_semantics.csv",
        "price_semantics.md",
        "schema.json",
    }
    gates = json.loads((output / "data_gate.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "audit_manifest.json").read_text(encoding="utf-8"))
    # 默认宇宙 all_a_liquid 仅依赖价格，Kronos 信号研究已不被 000300 PIT 阻塞。
    assert gates["kronos_signal_research_ready"] is True
    assert gates["research_backtest_ready"] is True
    assert gates["signal_research_ready"] is True
    assert gates["gates"]["pit_universe"]["status"] == "PARTIAL"
    # tradeability 覆盖齐全但滞后 => PARTIAL，realistic 可用但非实时辅助。
    assert gates["realistic_backtest_ready"] is True
    assert gates["formal_backtest_ready"] is False
    assert gates["fidelity"]["realistic_backtest_ready"] == "PARTIAL"
    # 000300 PIT 能力仍 PARTIAL（缺失 2015 起点 + 未更新到最新价），独立体现。
    assert gates["csi300_pit_ready"] is False
    assert gates["fidelity"]["csi300_pit_ready"] == "PARTIAL"
    assert gates["real_assist_data_ready"] is False
    assert manifest["run_start_commit"] == "abc123"
    assert manifest["run_end_commit"] == "abc123"
    assert manifest["generated_at"] == "2026-08-21T10:00:00+00:00"
    assert manifest["counts"] == {"action_events": 1, "pit_weeks": 1, "price_samples": 1}
    assert result["output_dir"] == str(output)
    for csv_path in output.glob("*.csv"):
        assert b"\r\n" not in csv_path.read_bytes()


def test_changed_dolt_head_refuses_to_publish_official_reports(tmp_path):
    output = tmp_path / "audit"

    with pytest.raises(DataVersionChangedError, match="abc123.*def456"):
        run_data_audit(
            HeadConnection(["abc123", "def456"]),
            provider=object(),
            output_dir=output,
            collect_fn=lambda connection, provider: audit_bundle(),
        )

    assert not output.exists()
