from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

from quantradar.audit import dolt_head_commit
from quantradar.kronos.runtime.contracts import LOOKBACK_DAYS, PREDICTION_DAYS
from quantradar.kronos.runtime.inputs import (
    FEATURE_NAMES,
    SymbolWindow,
    _collect_status,
    publish_input_package,
    select_eligible_windows,
    sha256_file,
)


def _date(value: dt.date | str) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(value)


def list_signal_dates(
    provider, *, start: dt.date | str, end: dt.date | str
) -> list[dt.date]:
    rows = provider.connection.query(
        "SELECT DISTINCT trade_date FROM ts_index_weight "
        "WHERE index_code = %s AND trade_date BETWEEN %s AND %s "
        "ORDER BY trade_date",
        ("000300.SH", _date(start).isoformat(), _date(end).isoformat()),
    )
    return [
        value
        for row in rows
        if isinstance((value := row.get("trade_date")), dt.date)
    ]


def collect_week_input_package(
    provider,
    *,
    signal_date: dt.date | str,
    output_dir: str | Path,
    data_contract_path: str | Path,
    expected_data_commit: str | None = None,
) -> dict:
    day = _date(signal_date)
    connection = provider.connection
    start_commit = dolt_head_commit(connection)
    if not start_commit or (
        expected_data_commit is not None and start_commit != expected_data_commit
    ):
        raise RuntimeError(
            f"Dolt HEAD does not match SignalRun snapshot: {start_commit} != {expected_data_commit}"
        )
    snapshot = connection.query_one(
        "SELECT COUNT(*) AS member_count FROM ts_index_weight "
        "WHERE index_code = %s AND trade_date = %s",
        ("000300.SH", day.isoformat()),
    ) or {}
    if int(snapshot.get("member_count") or 0) == 0:
        raise RuntimeError(f"No exact 000300.SH PIT snapshot for {day}")

    symbols = sorted(provider.get_index_stocks("000300.XSHG", date=day))
    statuses = _collect_status(connection, symbols, day)
    securities = provider.get_all_securities("stock", date=day)
    open_days = [item.date() for item in provider.get_trade_days(end_date=day)]
    future_dates = [
        item.date()
        for item in provider.get_trade_days(
            start_date=day + dt.timedelta(days=1), count=PREDICTION_DAYS
        )
    ]
    windows: list[SymbolWindow] = []
    for symbol in symbols:
        frame = provider.get_price(
            symbol,
            end_date=day,
            count=LOOKBACK_DAYS,
            fields=list(FEATURE_NAMES),
            fq="qfq",
            pre_factor_ref_date=day,
            fill_paused=False,
        )
        listed_start = None
        if symbol in securities.index:
            raw = securities.loc[symbol, "start_date"]
            if not pd.isna(raw):
                listed_start = pd.Timestamp(raw).date()
        listed_days = (
            sum(trade_day >= listed_start for trade_day in open_days)
            if listed_start is not None
            else 0
        )
        is_st, tradestatus = statuses.get(symbol, (None, None))
        windows.append(
            SymbolWindow(
                symbol=symbol,
                values=frame.loc[:, list(FEATURE_NAMES)].to_numpy(dtype="float64"),
                dates=tuple(index.date() for index in frame.index),
                listed_trade_days=listed_days,
                is_st=is_st,
                tradestatus=tradestatus,
            )
        )
    selection = select_eligible_windows(windows)
    end_commit = dolt_head_commit(connection)
    if end_commit != start_commit:
        raise RuntimeError(
            f"Dolt HEAD changed while building weekly input: {start_commit} -> {end_commit}"
        )
    manifest = publish_input_package(
        output_dir=output_dir,
        selection=selection,
        signal_date=day,
        future_dates=future_dates,
        pit_snapshot_date=day,
        data_commit=start_commit,
        data_contract_hash=sha256_file(data_contract_path),
    )
    manifest["execution_date"] = future_dates[0].isoformat()
    manifest_path = Path(output_dir) / "input_manifest.json"
    temporary = manifest_path.with_name(".input_manifest.json.tmp")
    import json
    import os

    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, manifest_path)
    return manifest
