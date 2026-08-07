import pandas as pd
import pytest

from bullet_trade.data.providers.tushare import TushareProvider


class DummyPro:
    def stock_basic(self, exchange="", list_status="L", fields=None):
        return pd.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "name": ["平安银行"],
                "list_date": [None],
                "delist_date": [None],
            }
        )

    def fund_basic(self, status="L", market="E", fields=None):
        return pd.DataFrame(
            {
                "ts_code": ["113000.SH"],
                "name": ["测试转债"],
                "found_date": [None],
                "delist_date": [None],
            }
        )

    def index_basic(self, market="SSE"):
        return pd.DataFrame(
            {
                "ts_code": ["000001.SH"],
                "fullname": ["测试指数"],
            }
        )


@pytest.mark.unit
def test_tushare_get_all_securities_handles_missing_dates(monkeypatch):
    provider = TushareProvider({"cache_dir": None})
    dummy = DummyPro()
    monkeypatch.setattr(provider, "_ensure_client", lambda: dummy)
    monkeypatch.setattr(provider._cache, "cached_call", lambda name, kwargs, fn, result_type=None: fn(kwargs))

    df = provider.get_all_securities(types=["stock", "fund", "index"], date=None)

    assert not df.empty
    assert "start_date" in df.columns
    assert "end_date" in df.columns

    info = provider.get_security_info("000001.XSHE")
    assert info.get("display_name")
