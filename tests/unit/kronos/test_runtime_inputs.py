from __future__ import annotations

import datetime as dt
import json

import numpy as np

from quantradar.kronos.runtime.inputs import (
    FEATURE_NAMES,
    SymbolWindow,
    array_content_hash,
    publish_input_package,
    select_eligible_windows,
    validate_window,
)


def _window(
    symbol: str,
    *,
    amount: float,
    listed_days: int = 200,
    is_st: bool | None = False,
    tradestatus: bool | None = True,
) -> SymbolWindow:
    rows = np.zeros((90, 6), dtype=np.float64)
    base = np.linspace(10.0, 11.0, 90)
    rows[:, 0] = base
    rows[:, 1] = base + 1.0
    rows[:, 2] = base - 1.0
    rows[:, 3] = base + 0.25
    rows[:, 4] = 1000.0
    rows[:, 5] = amount
    dates = tuple(dt.date(2022, 1, 1) + dt.timedelta(days=index) for index in range(90))
    return SymbolWindow(
        symbol=symbol,
        values=rows,
        dates=dates,
        listed_trade_days=listed_days,
        is_st=is_st,
        tradestatus=tradestatus,
    )


def test_validate_window_rejects_bad_ohlc_and_short_history() -> None:
    short = _window("000001.XSHE", amount=100.0)
    short.values = short.values[:-1]
    assert validate_window(short) == "expected 90 complete rows, got 89"

    bad = _window("000002.XSHE", amount=100.0)
    bad.values[3, 1] = bad.values[3, 2] - 0.1
    assert validate_window(bad) == "invalid OHLC structure"


def test_selection_excludes_known_bad_status_and_bottom_liquidity() -> None:
    windows = [
        _window(f"00000{index}.XSHE", amount=float(index))
        for index in range(1, 6)
    ]
    windows.append(_window("600001.XSHG", amount=100.0, is_st=True))
    windows.append(_window("600002.XSHG", amount=100.0, tradestatus=False))

    selection = select_eligible_windows(windows)

    assert [item.symbol for item in selection.eligible] == [
        "000002.XSHE",
        "000003.XSHE",
        "000004.XSHE",
        "000005.XSHE",
    ]
    assert selection.exclusions["000001.XSHE"] == "bottom 20 percent by 20-day amount"
    assert selection.exclusions["600001.XSHG"] == "known ST on signal date"
    assert selection.exclusions["600002.XSHG"] == "known non-trading on signal date"


def test_selection_keeps_unknown_status_as_partial() -> None:
    windows = [
        _window(f"60000{index}.XSHG", amount=float(index), is_st=None, tradestatus=None)
        for index in range(1, 6)
    ]

    selection = select_eligible_windows(windows)

    assert len(selection.eligible) == 4
    assert selection.partial_status_symbols == [
        "600002.XSHG",
        "600003.XSHG",
        "600004.XSHG",
        "600005.XSHG",
    ]


def test_array_content_hash_changes_with_values_not_layout_identity() -> None:
    first = np.arange(12, dtype=np.float32).reshape(2, 6)
    same = first.copy()
    changed = first.copy()
    changed[0, 0] += 1

    assert array_content_hash({"values": first}) == array_content_hash({"values": same})
    assert array_content_hash({"values": first}) != array_content_hash({"values": changed})


def test_publish_input_package_writes_hashed_real_arrays(tmp_path) -> None:
    windows = [_window(f"6000{index:02d}.XSHG", amount=float(index)) for index in range(1, 71)]
    selection = select_eligible_windows(windows)
    future_dates = [dt.date(2022, 7, 4) + dt.timedelta(days=index) for index in range(10)]

    manifest = publish_input_package(
        output_dir=tmp_path,
        selection=selection,
        signal_date=dt.date(2022, 7, 1),
        future_dates=future_dates,
        pit_snapshot_date=dt.date(2022, 7, 1),
        data_commit="abc123",
        data_contract_hash="contract123",
        available_pit_signal_weeks=131,
    )

    assert manifest["feature_names"] == list(FEATURE_NAMES)
    assert manifest["eligible_symbol_count"] == 56
    assert manifest["universe"] == "all_a_liquid"
    assert manifest["input_content_sha256"]
    assert manifest["npz_sha256"]
    assert manifest["available_pit_signal_weeks"] == 131
    saved = np.load(tmp_path / "runtime_inputs.npz", allow_pickle=False)
    assert saved["values"].shape == (56, 90, 6)
    assert saved["symbols"].tolist() == sorted(saved["symbols"].tolist())
    assert json.loads((tmp_path / "input_manifest.json").read_text())["data_commit"] == "abc123"
