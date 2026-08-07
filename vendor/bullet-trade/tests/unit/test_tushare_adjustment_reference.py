from datetime import datetime

import pandas as pd
import pytest

from bullet_trade.data.providers.tushare import TushareProvider


@pytest.mark.unit
def test_tushare_prefactor_uses_latest_trade_day(monkeypatch):
    provider = TushareProvider({"cache_dir": None})

    df = pd.DataFrame(
        {
            "open": [10.0],
            "high": [10.0],
            "low": [10.0],
            "close": [10.0],
        },
        index=pd.to_datetime(["2025-07-01"]),
    )

    calls = []

    def fake_fetch_adj_factor(security, start_dt, end_dt):
        start_dt = pd.to_datetime(start_dt)
        end_dt = pd.to_datetime(end_dt)
        calls.append((start_dt.date(), end_dt.date()))
        if start_dt.date() == datetime(2025, 7, 2).date() and end_dt.date() == datetime(2025, 7, 2).date():
            return pd.DataFrame({"trade_date": ["20250702"], "adj_factor": [0.98]})
        return pd.DataFrame({"trade_date": ["20250701"], "adj_factor": [1.0]})

    monkeypatch.setattr(provider, "_fetch_adj_factor", fake_fetch_adj_factor)
    monkeypatch.setattr(provider, "get_trade_days", lambda start_date=None, end_date=None, count=None: [datetime(2025, 7, 2)])

    adjusted = provider._apply_adjustment("000001.XSHE", df, "pre", pre_factor_ref_date=None)

    assert adjusted.loc[pd.Timestamp("2025-07-01"), "close"] != df.loc[pd.Timestamp("2025-07-01"), "close"]
    assert (datetime(2025, 7, 2).date(), datetime(2025, 7, 2).date()) in calls
