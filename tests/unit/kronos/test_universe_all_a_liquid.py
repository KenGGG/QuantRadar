from __future__ import annotations

import datetime as dt

import pandas as pd

from quantradar.kronos.runtime.contracts import LOOKBACK_DAYS, PREDICTION_DAYS
from quantradar.kronos.runtime.inputs import FEATURE_NAMES
from quantradar.kronos.signal.inputs import collect_week_input_package
from quantradar.kronos.universe_spec import Universe


class _AllLiquidConnection:
    """最小可用连接：支撑 all_a_liquid 路径（不查指数 PIT）。"""

    def __init__(self, symbols, as_of):
        self._symbols = list(symbols)
        self._as_of = as_of
        self.dolt = "fake-commit"

    def query_one(self, sql: str, params=None):
        if "dolt_log" in sql:
            return {"commit_hash": self.dolt}
        if "COUNT(DISTINCT tradedate)" in sql:
            return {"n": 200}
        return None

    def query(self, sql: str, params=None):
        if "ts_index_weight" in sql:
            return [{"member_count": 0}]
        if "final_a_stock_eod_price" in sql and "DISTINCT symbol" in sql:
            return [{"symbol": s} for s in self._symbols]
        # _collect_status 的 bao 查询：无状态数据。
        return []


def _trade_days_ending(day: dt.date, count: int) -> list[dt.datetime]:
    return [
        dt.datetime.combine(day - dt.timedelta(days=count - 1 - i), dt.time())
        for i in range(count)
    ]


class _AllLiquidProvider:
    def __init__(self, symbols, as_of):
        self.connection = _AllLiquidConnection(symbols, as_of)
        self._as_of = as_of

    def get_trade_days(self, *, end_date=None, start_date=None, count=None):
        if start_date is not None and count is not None:
            base = dt.date.fromisoformat(str(start_date))
            return [dt.datetime.combine(base + dt.timedelta(days=i), dt.time()) for i in range(count)]
        base = dt.date.fromisoformat(str(end_date))
        return _trade_days_ending(base, LOOKBACK_DAYS)

    def get_price(self, symbol, *, end_date, count, fields, fq, pre_factor_ref_date, fill_paused):
        day = dt.date.fromisoformat(str(end_date))
        dates = _trade_days_ending(day, count)
        base = [10.0 + i * 0.01 for i in range(count)]
        return pd.DataFrame(
            {
                "open": base,
                "high": [v + 1.0 for v in base],
                "low": [v - 1.0 for v in base],
                "close": [v + 0.25 for v in base],
                "volume": [1000.0] * count,
                "amount": [1_000_000.0] * count,
            },
            index=pd.to_datetime(dates),
        )


def test_collect_week_package_all_a_liquid_builds_without_pit_snapshot(tmp_path):
    symbols = [f"SH{600000 + i:06d}" for i in range(70)]
    as_of = dt.date(2022, 7, 1)
    provider = _AllLiquidProvider(symbols, as_of)

    manifest = collect_week_input_package(
        provider,
        signal_date=as_of,
        output_dir=tmp_path,
        data_contract_path="reports/kronos/data_audit/data_contract.json",
        universe=Universe.ALL_A_LIQUID,
    )

    assert manifest["universe"] == "all_a_liquid"
    assert manifest["pit_snapshot_date"] == as_of.isoformat()
    # 70 标的、流动性取前 80% => 56 eligible（>=50）。
    assert manifest["eligible_symbol_count"] >= 50
    assert manifest["tradeability_status"] == "PARTIAL"


def test_collect_week_package_csi300_pit_without_snapshot_raises(tmp_path):
    provider = _AllLiquidProvider([], dt.date(2022, 7, 1))
    try:
        collect_week_input_package(
            provider,
            signal_date=dt.date(2022, 7, 1),
            output_dir=tmp_path,
            data_contract_path="reports/kronos/data_audit/data_contract.json",
            universe=Universe.CSI300_PIT,
        )
        raise AssertionError("expected RuntimeError for missing CSI300 PIT snapshot")
    except RuntimeError as exc:
        assert "000300.SH" in str(exc)
