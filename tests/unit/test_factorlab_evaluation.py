from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quantradar.factorlab.evaluation import dates_within_label_window, evaluate, forward_open_label, split_dates


def test_labels_never_use_same_day_open():
    values = pd.DataFrame({"a": range(10), "b": range(10, 20)}, index=pd.date_range("2020-01-01", periods=10))
    labels = forward_open_label(values, 1)
    assert labels.iloc[0, 0] == values.iloc[2, 0] / values.iloc[1, 0] - 1
    assert pd.isna(labels.iloc[-2, 0])


def test_evaluation_requires_full_cross_section_and_full_rolling_window():
    dates = pd.date_range("2020-01-01", periods=61)
    columns = [f"s{i:02}" for i in range(20)]
    data = np.tile(np.arange(20, dtype=float), (61, 1))
    result = evaluate(pd.DataFrame(data, index=dates, columns=columns), pd.DataFrame(data, index=dates, columns=columns))
    assert result["valid_dates"] == 61
    assert result["rolling_60d_ic"][58] is None
    assert result["rolling_60d_ic"][59] == 1.0
    assert result["rank_ic_positive_ratio"] == 1.0
    assert result["rank_ic_positive_month_ratio"] == 1.0
    assert len(result["monthly_rank_ic"]) == 3
    assert result["mean_cross_section"] == 20.0
    assert result["top_quantile_turnover"] == 0.0


def test_split_excludes_labels_that_cross_a_boundary():
    dates = pd.date_range("2024-01-01", periods=20, freq="B")
    splits = split_dates(dates)
    assert [len(splits[x]) for x in ("research", "validation", "holdout")] == [12, 4, 4]
    assert dates[11] not in dates_within_label_window(splits["research"], dates, 1)
    assert dates[16] in dates_within_label_window(splits["holdout"], dates, 1)


def test_split_requires_a_complete_positive_partition():
    with pytest.raises(ValueError):
        split_dates(pd.date_range("2024-01-01", periods=10), (.5, .5, .5))


def test_factor_preflight_reports_missing_input_without_rejecting_other_formulas():
    from quantradar.factorlab.qualification import preflight

    ready = preflight({"open", "high", "low", "close", "volume", "amount", "vwap", "returns", "universe"}, {"open", "close"})
    blocked = preflight({"open", "close", "universe"}, {"open", "cap"})

    assert ready == {"status": "READY", "missing_fields": []}
    assert blocked == {"status": "BLOCKED_INPUT", "missing_fields": ["cap"]}


def test_factor_preflight_rejects_all_empty_required_input():
    from quantradar.factorlab.qualification import preflight
    panel = {"close": pd.DataFrame([[float("nan")]]), "universe": pd.DataFrame([[True]])}
    assert preflight({"close", "universe"}, {"close"}, panel=panel)["status"] == "BLOCKED_INPUT"


def test_industry_inputs_require_a_versioned_dictionary_not_only_code_prefixes():
    from quantradar.factorlab.qualification import qualified_industry_fields

    assert qualified_industry_fields({"metadata": {"sw_industry_hierarchy": {
        "levels": "derived from preserved six-digit code", "raw_sha256": "a" * 64,
    }}}) == set()
    assert qualified_industry_fields({"metadata": {"sw_industry_hierarchy": {
        "dictionary_version": "sw-2021-v1", "levels": ["L1", "L2", "L3"],
    }}}) == {"indclass.sector", "indclass.industry", "indclass.subindustry"}


def test_factor_batch_status_distinguishes_data_blocks_from_engine_failures():
    from quantradar.factorlab.qualification import batch_status

    assert batch_status(["COMPUTED", "BLOCKED_INPUT"]) == "PARTIAL_SUCCESS"
    assert batch_status(["BLOCKED_INPUT", "BLOCKED_WARMUP"]) == "BLOCKED"
    assert batch_status(["COMPUTED", "FAILED_ENGINE"]) == "FAILED"


def test_factor_result_summary_keeps_blocked_item_without_evaluations():
    from quantradar.factorlab.service import result_summary_items

    assert result_summary_items([
        {"alpha_id": 1, "status": "COMPUTED", "evaluations": {"1": {"summary": {"valid_dates": 2}}}},
        {"alpha_id": 58, "status": "BLOCKED_INPUT", "missing_fields": ["indclass.sector"]},
    ]) == [
        {"alpha_id": 1, "status": "COMPUTED", "evaluations": {"1": {"valid_dates": 2}}},
        {"alpha_id": 58, "status": "BLOCKED_INPUT", "missing_fields": ["indclass.sector"]},
    ]


def test_calculation_start_uses_fixed_trading_sessions_not_calendar_days():
    from quantradar.factorlab.service import calculation_start_from_calendar

    calendar = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"]
    assert calculation_start_from_calendar(calendar, "2024-01-08", 3) == "2024-01-04"
    assert calculation_start_from_calendar(calendar, "2024-01-03", 20) == "2024-01-02"


def test_factor_preflight_reports_insufficient_trading_session_warmup():
    from quantradar.factorlab.qualification import preflight

    outcome = preflight(
        {"open", "close"}, {"open", "close"},
        panel_dates=pd.date_range("2024-01-02", periods=2, freq="B"),
        requested_dates=pd.date_range("2024-01-03", periods=1, freq="B"),
        lookback_days=3,
    )
    assert outcome == {"status": "BLOCKED_WARMUP", "missing_fields": [], "warmup_available": 2, "warmup_required": 3}


def test_failed_engine_item_preserves_the_formula_and_error():
    from quantradar.factorlab.service import failed_engine_item

    item = failed_engine_item(56, RuntimeError("broken interpreter"))
    assert item == {"alpha_id": 56, "status": "FAILED_ENGINE", "error": "RuntimeError: broken interpreter"}


def test_engine_failure_does_not_stop_later_independent_formula(monkeypatch, tmp_path):
    from quantradar.factorlab import service
    from quantradar.datahub.alpha101 import catalog as alpha_catalog
    from quantradar import storage

    dates = pd.date_range("2024-01-02", periods=60, freq="B")
    columns = [f"{i:06}.SZ" for i in range(20)]
    panel = {name: pd.DataFrame(10.0, index=dates, columns=columns)
             for name in ("open", "high", "low", "close", "volume", "amount", "vwap", "returns")}
    panel["universe"] = pd.DataFrame(True, index=dates, columns=columns)
    updates = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(service, "_panel", lambda config: (panel, panel["open"]))
    monkeypatch.setattr(storage, "update_experiment", lambda *args, **kwargs: updates.append(kwargs["config"].copy()))
    monkeypatch.setattr(alpha_catalog, "dependency_matrix", lambda: [
        {"alpha_id": 1, "fields": ["open"], "lookback_days": 1, "formula_hash": "a", "semantics_version": "v"},
        {"alpha_id": 2, "fields": ["open"], "lookback_days": 1, "formula_hash": "b", "semantics_version": "v"},
    ])

    def compute(alpha_id, *_args, **_kwargs):
        if alpha_id == 1:
            raise RuntimeError("interpreter fault")
        return pd.DataFrame(np.tile(np.arange(20, dtype=float), (len(dates), 1)), index=dates, columns=columns)

    monkeypatch.setattr(alpha_catalog, "compute", compute)
    config = {"status": "PENDING", "items": [], "alpha_ids": [1, 2], "horizons": [1],
              "split_ratios": [.6, .2, .2], "start_date": "2024-01-02", "end_date": "2024-03-25",
              "calculation_start": "2024-01-02", "release_id": "R1", "base_commit": "b",
              "supplemental_commit": "s", "members_hash": "m", "pool_type": "CUSTOM_STATIC_POOL",
              "snapshot_date": None, "price_mode": "RAW", "unit_contract": "u", "adv_basis": "amount",
              "operator_bundle_hash": "o", "research_input_version": "r", "min_cross_section": 20}
    service._run("batch-1", config)

    assert config["status"] == "FAILED"
    assert [(item["alpha_id"], item["status"]) for item in config["items"]] == [(1, "FAILED_ENGINE"), (2, "COMPUTED")]


def test_factorlab_price_rows_use_release_provider_and_native_units():
    from quantradar.factorlab.service import provider_price_rows

    dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
    columns = pd.MultiIndex.from_product([["open", "high", "low", "close", "volume", "amount"], ["000001.XSHE"]], names=["field", "security"])
    wide = pd.DataFrame([[1, 2, .5, 1.5, 100, 150], [2, 3, 1, 2.5, 200, 500]], index=dates, columns=columns)

    class Provider:
        def get_price(self, securities, **kwargs):
            assert securities == ["000001.XSHE"]
            assert kwargs == {"start_date": "2024-01-02", "end_date": "2024-01-03", "frequency": "daily", "fields": ["open", "high", "low", "close", "volume", "amount"]}
            return wide

    rows = provider_price_rows(Provider(), ["000001.SZ"], "2024-01-02", "2024-01-03")
    assert rows["000001.SZ"][0] == {"open": 1, "high": 2, "low": .5, "close": 1.5, "volume": 100, "amount": 150, "trade_date": dates[0], "unit_contract_version": "joinquant-shares-yuan-v2"}


def test_universe_mask_uses_explicit_lifecycle_not_price_presence():
    from quantradar.factorlab.service import lifecycle_universe

    dates = pd.date_range("2024-01-02", periods=4, freq="B")
    mask = lifecycle_universe(dates, ["000001.SZ", "000002.SZ"], [
        {"symbol": "000001.SZ", "list_date": "2024-01-03", "delist_date": None},
        {"symbol": "000002.SZ", "list_date": "2020-01-01", "delist_date": "2024-01-05"},
    ])
    assert mask["000001.SZ"].tolist() == [False, True, True, True]
    assert mask["000002.SZ"].tolist() == [True, True, True, False]
