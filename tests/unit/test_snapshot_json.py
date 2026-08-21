from __future__ import annotations

import datetime as dt
import json

from quantradar.snapshot import write_snapshot_json


def test_snapshot_writer_serializes_nested_dates_and_returns_native_payload(tmp_path):
    path = tmp_path / "snapshot.json"
    native = write_snapshot_json(
        path,
        {
            "config": {"signal_date": dt.date(2022, 6, 30)},
            "records": [{"day": dt.date(2022, 7, 1)}],
        },
    )
    assert native == {
        "config": {"signal_date": "2022-06-30 00:00:00"},
        "records": [{"day": "2022-07-01 00:00:00"}],
    }
    assert json.loads(path.read_text()) == native
