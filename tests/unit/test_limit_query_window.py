import pandas as pd
import pytest
from quantradar.providers.investment_data.provider import InvestmentDataProvider


@pytest.mark.parametrize('dates', [['2023-08-30', '2023-08-31'], []])
def test_limit_query_only_reads_price_window(monkeypatch, dates):
    provider = InvestmentDataProvider()
    calls = []
    def fetch(table, cols, symbol, start, end, count, fill_paused):
        calls.append((start, end, count))
        if len(calls) == 1:
            return pd.DataFrame({'close': [8.1] * len(dates)}, index=pd.to_datetime(dates))
        assert (start, end, count) == ('2023-08-30', '2023-08-31', None)
        return pd.DataFrame({'up_limit': [8.9]}, index=pd.to_datetime(['2023-08-31']))
    monkeypatch.setattr(provider, '_fetch_table_cols', fetch)
    result = provider._fetch_raw_price('SH600011', ['close'], ['up_limit'], False,
                                       None, '2023-08-31', 2, False)
    assert len(calls) == (2 if dates else 1)
    assert list(result.columns) == ['close', 'up_limit']
    if dates:
        assert pd.isna(result.iloc[0]['up_limit'])
        assert result.iloc[-1]['up_limit'] == 8.9
