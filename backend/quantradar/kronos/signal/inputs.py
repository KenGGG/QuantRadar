from __future__ import annotations

import datetime as dt
import json
import os
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
from quantradar.kronos.universe_spec import (
    DEFAULT_UNIVERSE,
    INDEX_CODE,
    JQ_INDEX_CODE,
    Universe,
    all_a_liquid_symbols,
    listed_trade_days,
    list_signal_dates as _spec_list_signal_dates,
)
from quantradar.providers.investment_data.symbols import to_joinquant_symbol


def _date(value: dt.date | str) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(value)


def list_signal_dates(
    provider,
    *,
    start: dt.date | str,
    end: dt.date | str,
    universe: Universe = DEFAULT_UNIVERSE,
) -> list[dt.date]:
    """周度信号日；委托给 universe_spec（默认 all_a_liquid，不查指数 PIT）。"""
    return _spec_list_signal_dates(provider, start=start, end=end, universe=universe)


def collect_week_input_package(
    provider,
    *,
    signal_date: dt.date | str,
    output_dir: str | Path,
    data_contract_path: str | Path,
    expected_data_commit: str | None = None,
    universe: Universe = DEFAULT_UNIVERSE,
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

    if universe is Universe.ALL_A_LIQUID:
        internal_symbols = all_a_liquid_symbols(connection, day)
        jq_by_internal = {sym: to_joinquant_symbol(sym) for sym in internal_symbols}
        symbols = [jq_by_internal[sym] for sym in internal_symbols]
        statuses = _collect_status(connection, symbols, day)
        securities = None
    else:
        index_code = INDEX_CODE[universe]
        snapshot = connection.query_one(
            "SELECT COUNT(*) AS member_count FROM ts_index_weight "
            "WHERE index_code = %s AND trade_date = %s",
            (index_code, day.isoformat()),
        ) or {}
        if int(snapshot.get("member_count") or 0) == 0:
            raise RuntimeError(f"No exact {index_code} PIT snapshot for {day}")
        symbols = sorted(provider.get_index_stocks(JQ_INDEX_CODE[universe], date=day))
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
    candidate_symbols = (
        internal_symbols if universe is Universe.ALL_A_LIQUID else symbols
    )
    for source in candidate_symbols:
        if universe is Universe.ALL_A_LIQUID:
            jq_symbol = jq_by_internal[source]
            listed_days = listed_trade_days(connection, source, day)
        else:
            jq_symbol = source
            listed_start = None
            if source in securities.index:
                raw = securities.loc[source, "start_date"]
                if not pd.isna(raw):
                    listed_start = pd.Timestamp(raw).date()
            listed_days = (
                sum(trade_day >= listed_start for trade_day in open_days)
                if listed_start is not None
                else 0
            )
        frame = provider.get_price(
            jq_symbol,
            end_date=day,
            count=LOOKBACK_DAYS,
            fields=list(FEATURE_NAMES),
            fq="qfq",
            pre_factor_ref_date=day,
            fill_paused=False,
        )
        is_st, tradestatus = statuses.get(jq_symbol, (None, None))
        windows.append(
            SymbolWindow(
                symbol=jq_symbol,
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
        universe=universe,
    )
    manifest["execution_date"] = future_dates[0].isoformat()
    manifest_path = Path(output_dir) / "input_manifest.json"
    temporary = manifest_path.with_name(".input_manifest.json.tmp")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, manifest_path)
    return manifest
