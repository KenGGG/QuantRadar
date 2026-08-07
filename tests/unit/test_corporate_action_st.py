"""Phase 5 完整性（目标口径）—— 公司行为 + ST 状态（DB-backed，无 mock）。

数据源：bao_a_stock_eod_info（真实 is_st / tradestatus / preclose / adjfactor）。

- get_split_dividend：以「preclose(D) != close(D-1)」识别除权除息日，除权缺口 =
  每股税前红利；与原始表字段对账（以 600519 2022-06-30 已知分红验证）。
- get_extras('is_st') / get_extras('tradestatus')：直接读真实列，与 bao_a_stock_eod_info
  逐行对账（含一个确为 ST 的标的 SH600078）。
"""

from __future__ import annotations

import pandas as pd
import pytest

from backend.quantradar.bootstrap import bootstrap_investment_data
from backend.quantradar.config import load_investment_data_config
from backend.quantradar.providers.investment_data.connection import (
    InvestmentDataConnection,
)
from backend.quantradar.providers.investment_data.provider import _INFO_TABLE

# 600519 2021 年报：股权登记 2022-06-29，除权除息 2022-06-30，每股派发现金红利 21.675 元
DIV_SECURITY = "600519.XSHG"
DIV_EX_DATE = "2022-06-30"
DIV_PREV_CLOSE = 2030.00   # 2022-06-29 close
DIV_PRECLOSE = 2008.33     # 2022-06-30 preclose（除权参考价）

# 确为 ST 的标的（bao_a_stock_eod_info.is_st=1 @ 2023-03-01）
ST_SECURITY = "SH600078"
ST_JQ = "600078.XSHG"


@pytest.mark.unit
class TestCorporateAction:
    def test_ex_date_detected(self):
        p = bootstrap_investment_data(set_active=True, overwrite=True)
        events = p.get_split_dividend(DIV_SECURITY, "2022-06-01", "2022-07-31")
        assert any(e["date"] == DIV_EX_DATE for e in events), "未识别 600519 2022-06-30 除权日"

    def test_dividend_gap_equals_preclose_drop(self):
        """除权缺口（close(D-1) - preclose(D)）应等于原始表 2022-06-29/06-30 之差。"""
        p = bootstrap_investment_data(set_active=True, overwrite=True)
        events = p.get_split_dividend(DIV_SECURITY, "2022-06-01", "2022-07-31")
        ev = next(e for e in events if e["date"] == DIV_EX_DATE)
        expected_gap = round(DIV_PREV_CLOSE - DIV_PRECLOSE, 6)
        assert abs(ev["bonus_pre_tax"] - expected_gap) < 1e-3, (
            f"bonus_pre_tax={ev['bonus_pre_tax']} 与真实除权缺口 {expected_gap} 不符"
        )
        # 与原始 bao_a_stock_eod_info 对账
        c = InvestmentDataConnection(load_investment_data_config())
        prev = c.query_one(
            "SELECT close FROM bao_a_stock_eod_info WHERE symbol=%s AND tradedate=%s",
            ("SH600519", "2022-06-29"),
        )["close"]
        pre = c.query_one(
            "SELECT preclose FROM bao_a_stock_eod_info WHERE symbol=%s AND tradedate=%s",
            ("SH600519", "2022-06-30"),
        )["preclose"]
        assert abs((prev - pre) - ev["bonus_pre_tax"]) < 1e-3

    def test_event_fields_for_engine(self):
        """引擎依赖的字段齐备：date / scale_factor / bonus_pre_tax / security_type / per_base。"""
        p = bootstrap_investment_data(set_active=True, overwrite=True)
        events = p.get_split_dividend(DIV_SECURITY, "2022-06-01", "2022-07-31")
        ev = next(e for e in events if e["date"] == DIV_EX_DATE)
        assert ev["scale_factor"] == 1.0
        assert ev["security_type"] == "stock"
        assert ev["per_base"] == 10
        assert "_source" in ev and "_partial" in ev  # 透明标记 PARTIAL

    def test_requires_boundary(self):
        p = bootstrap_investment_data(set_active=True, overwrite=True)
        with pytest.raises(ValueError):
            p.get_split_dividend(DIV_SECURITY)  # 无边界 -> ValueError


@pytest.mark.unit
class TestExtrasST:
    def test_is_st_normal_stock_is_zero(self):
        p = bootstrap_investment_data(set_active=True, overwrite=True)
        df = p.get_extras("is_st", DIV_SECURITY, "2023-01-03", "2023-03-31", df=True)
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == [DIV_SECURITY]
        assert (df[DIV_SECURITY] == 0).all(), "600519 非 ST，is_st 应全为 0"

    def test_is_st_st_stock_is_one(self):
        p = bootstrap_investment_data(set_active=True, overwrite=True)
        df = p.get_extras("is_st", ST_JQ, "2023-03-01", "2023-03-01", df=True)
        assert df[ST_JQ].iloc[0] == 1.0, "SH600078 @ 2023-03-01 应为 ST（is_st=1）"
        # 与原始表对账
        c = InvestmentDataConnection(load_investment_data_config())
        raw = c.query_one(
            "SELECT is_st FROM bao_a_stock_eod_info WHERE symbol=%s AND tradedate=%s",
            (ST_SECURITY, "2023-03-01"),
        )["is_st"]
        assert int(raw) == 1

    def test_tradestatus_alias(self):
        p = bootstrap_investment_data(set_active=True, overwrite=True)
        df = p.get_extras("tradestatus", DIV_SECURITY, "2023-01-03", "2023-01-05", df=True)
        assert (df[DIV_SECURITY] == 1).all(), "600519 正常交易日 tradestatus 应为 1"
        # 'pause' 别名应等价
        df2 = p.get_extras("pause", DIV_SECURITY, "2023-01-03", "2023-01-05", df=True)
        pd.testing.assert_frame_equal(df, df2)

    def test_get_extras_dict_mode(self):
        p = bootstrap_investment_data(set_active=True, overwrite=True)
        d = p.get_extras("is_st", [DIV_SECURITY], "2023-01-03", "2023-01-04", df=False)
        assert DIV_SECURITY in d
        assert all(v == 0 for v in d[DIV_SECURITY].values())

    def test_unsupported_extras_field(self):
        p = bootstrap_investment_data(set_active=True, overwrite=True)
        with pytest.raises(ValueError):
            p.get_extras("fq", DIV_SECURITY, "2023-01-03", "2023-01-04")
