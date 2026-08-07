import pandas as pd
import pytest

from bullet_trade.research.factors import (
    BacktestConfig,
    CostConfig,
    FactorPipelineConfig,
    FilterConfig,
    evaluate_factor_performance,
    run_factor_pipeline,
    save_results,
    load_results,
)


def _sample_df():
    rows = []
    dates = pd.date_range("2025-01-01", periods=3, freq="D")
    codes = ["110001.XSHG", "113001.XSHE", "128001.XSHE"]
    for dt in dates:
        for idx, code in enumerate(codes):
            close = 100 + idx * 5 + dt.day % 2
            conv_price = 12 + idx
            stock_close = 10 + idx * 0.5
            conversion_value = 100 * stock_close / conv_price
            premium = (close - conversion_value) / conversion_value
            forward_return = 0.001 * (idx - 1)
            rows.append(
                {
                    "date": dt,
                    "code": code,
                    "close": close,
                    "stock_close": stock_close,
                    "convert_price": conv_price,
                    "conversion_value": conversion_value,
                    "premium_ratio": premium,
                    "double_low": close + premium * 100,
                    "forward_return": forward_return,
                    "paused": False,
                    "is_st": False,
                    "list_date": pd.Timestamp("2024-01-01"),
                    "maturity_date": pd.Timestamp("2027-12-31"),
                    "market_cap": 5e9 + idx * 1e8,
                    "industry": "sector_" + ("A" if idx % 2 == 0 else "B"),
                }
            )
    return pd.DataFrame(rows)


def test_factor_pipeline_and_filtering():
    df = _sample_df()
    factor_funcs = {"conv_prem": lambda d: d["premium_ratio"], "double_low": lambda d: -d["double_low"]}
    cfg = FactorPipelineConfig(
        factor_funcs=factor_funcs,
        filter_config=FilterConfig(skip_paused=True, skip_st=True, min_maturity_days=100),
        winsor_limits=(0.05, 0.95),
        standardize="zscore",
        neutralize_industry=True,
        neutralize_mcap=True,
    )
    result = run_factor_pipeline(df, cfg)
    assert not result.data["conv_prem"].isna().all()
    assert "composite_score" in result.data
    assert result.filter_counts["kept"] == len(df)


def test_evaluation_with_costs():
    df = _sample_df()
    factor_funcs = {"conv_prem": lambda d: d["premium_ratio"]}
    pipeline_result = run_factor_pipeline(
        df,
        FactorPipelineConfig(factor_funcs=factor_funcs, filter_config=FilterConfig(), standardize="rank"),
    )
    eval_cfg = BacktestConfig(n_buckets=3, long_buckets=[3], short_buckets=[1], factor_col="composite_score")
    cost_cfg = CostConfig(fixed_fee=0.1, commission_buy=0.0005, commission_sell=0.0005, tax_sell=0.001)
    evaluation = evaluate_factor_performance(pipeline_result.data, eval_cfg, cost_cfg)
    assert not evaluation.bucket_returns.empty
    assert "net_return" in evaluation.portfolio_returns.columns
    assert "ic_mean" in evaluation.metrics


def test_io_roundtrip(tmp_path):
    df = _sample_df()
    factor_funcs = {"conv_prem": lambda d: d["premium_ratio"]}
    pipeline_result = run_factor_pipeline(
        df, FactorPipelineConfig(factor_funcs=factor_funcs, filter_config=FilterConfig())
    )
    eval_cfg = BacktestConfig(n_buckets=3)
    evaluation = evaluate_factor_performance(pipeline_result.data, eval_cfg)
    saved = save_results(evaluation, output_dir=tmp_path, name="demo", formats=("csv",))
    assert saved
    loaded = load_results(tmp_path)
    assert "data" in loaded or "meta" in loaded
