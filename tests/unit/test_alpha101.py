"""Synthetic formula/operator tests; these establish no real-data qualification."""
import importlib
from collections import Counter

import numpy as np
import pandas as pd
import pytest


def api():
    try:
        return importlib.import_module('quantradar.datahub.alpha101')
    except ModuleNotFoundError:
        pytest.fail('Alpha101 catalogue and safe interpreter are not implemented')


def frame(values):
    return pd.DataFrame(values, dtype=float)


def test_full_catalogue_and_expression_dependencies():
    rows = api().dependency_matrix()
    assert [r['alpha_id'] for r in rows] == list(range(1, 102))
    assert Counter(r['group'] for r in rows) == {'price_volume': 82, 'industry': 18, 'market_cap': 1}
    assert set(rows[55]['fields']) == {'returns', 'cap'}
    assert 'indclass.subindustry' in rows[47]['fields']
    assert 'indclass.sector' in rows[57]['fields']
    assert 'indclass.industry' in rows[58]['fields']
    assert {'indclass.sector', 'indclass.subindustry'} <= set(rows[66]['fields'])
    assert all(len(r['formula_hash']) == 64 for r in rows)
    assert {r['alpha_id'] for r in rows if r['delay_adaptation'] == 'delay0_to_next_session'} == {42, 48, 53, 54}


def test_nested_warmup_counts_underlying_close_for_returns():
    rows = {r['alpha_id']: r for r in api().dependency_matrix()}
    assert rows[1]['lookback_days'] == 25  # returns 2 + stddev 19 + argmax 4
    assert rows[19]['lookback_days'] == 251
    assert rows[24]['lookback_days'] == 200
    assert rows[32]['lookback_days'] == 235
    assert rows[48]['lookback_days'] == 252
    assert rows[63]['lookback_days'] == 239  # ADV180 + sum36 + corr12 + decay11
    assert rows[96]['lookback_days'] == 101  # ADV60 + rank3 + corr2 + argmax11 + decay13 + rank12


def test_cross_section_rank_and_single_security_ts_rank():
    a = api()
    x = frame([[3, 1, 1], [1, 3, 1], [2, 2, 4]])
    got = a.evaluate('rank(close)', {'close': x})
    np.testing.assert_allclose(got.iloc[0], [1, .5, .5])
    ts = a.evaluate('ts_rank(close, 3.9)', {'close': x[[0]]})
    assert ts.iloc[:2].isna().all().all()
    assert ts.iloc[2, 0] == pytest.approx(2 / 3)


@pytest.mark.parametrize('expression', [
    '__import__(1)', 'close.__class__', 'close[0]', 'unknown(close)',
    'delay(close, -1)', 'sum(close, 0.5)', 'sum(close, volume)',
    'close +', 'rank(close, volume)', 'close; open',
])
def test_restricted_parser_rejects_invalid_expressions(expression):
    with pytest.raises(ValueError):
        api().evaluate(expression, {'close': frame([[1], [2]])})


def test_missing_field_and_misaligned_panel_fail_explicitly():
    with pytest.raises(ValueError, match='cap'):
        api().compute(56, {'returns': frame([[.1], [.2]])})
    with pytest.raises(ValueError, match='align'):
        api().compute(6, {'open': frame([[1], [2]]), 'volume': frame([[1]])})


def test_no_fill_no_partial_windows_no_shrinking_cross_section():
    a = api()
    x = frame([[1, 2], [np.nan, 3], [3, 4], [4, 5], [5, 6]])
    got = a.evaluate('sum(close, 3)', {'close': x})
    assert got.iloc[:4, 0].isna().all()
    assert got.iloc[4, 0] == 12
    assert a.evaluate('rank(close)', {'close': x}).iloc[1].isna().all()
    assert a.evaluate('close < 3', {'close': x}).iloc[1, 0] != 0
    assert np.isnan(a.evaluate('(close < 3) ? 1 : -1', {'close': x}).iloc[1, 0])


def test_zero_divisor_zero_variance_and_linear_decay():
    a = api()
    x = frame([[1], [2], [3]])
    p = {'close': x, 'volume': frame([[0], [0], [0]])}
    assert a.evaluate('close / volume', p).isna().all().all()
    assert a.evaluate('correlation(close, volume, 3)', p).isna().all().all()
    assert a.evaluate('decay_linear(close, 3)', p).iloc[-1, 0] == pytest.approx(14 / 6)
    assert a.evaluate('ts_argmax(close, 3)', p).iloc[-1, 0] == 3


def test_alpha_1_6_101_hand_examples():
    a = api()
    close = pd.DataFrame(np.tile([2., 3., 4.], (25, 1)))
    close.iloc[-5:] = [[9, 1, 1], [1, 8, 2], [2, 3, 9], [3, 4, 3], [4, 5, 4]]
    returns = close * 0 + .01
    result = a.compute(1, {'close': close, 'returns': returns})
    assert result.iloc[:24].isna().all().all()
    np.testing.assert_allclose(result.iloc[-1], [-1/6, 1/6, .5])
    op = frame([[i, 11-i] for i in range(1, 11)])
    vol = frame([[i * 2, i * 3] for i in range(1, 11)])
    np.testing.assert_allclose(a.compute(6, {'open': op, 'volume': vol}).iloc[-1], [-1, 1])
    p = {'open': frame([[10]]), 'close': frame([[12]]), 'high': frame([[13]]), 'low': frame([[9]])}
    assert a.compute(101, p).iloc[0, 0] == pytest.approx(2 / 4.001)


def test_adv_versions_are_distinct_and_missing_basis_is_explicit():
    a = api()
    p = {'volume': frame([[i] for i in range(1, 21)]), 'amount': frame([[i * 10] for i in range(1, 21)])}
    assert a.evaluate('adv20', p).iloc[-1, 0] == 105
    assert a.evaluate('adv20', p, adv_basis='volume').iloc[-1, 0] == 10.5
    with pytest.raises(ValueError, match='amount'):
        a.evaluate('adv20', {'volume': p['volume']})
    with pytest.raises(ValueError, match='adv_basis'):
        a.evaluate('adv20', p, adv_basis='guess')


def test_primary_source_panel_minmax_interpretation_is_versioned():
    rows = api().dependency_matrix()
    expected = {71, 73, 76, 77, 82, 87, 88, 92, 96}
    assert {r['alpha_id'] for r in rows if 'panel_minmax_elementwise' in r['semantic_adaptations']} == expected
    a = api()
    p = {'close': frame([[3], [1], [2]]), 'open': frame([[1], [2], [3]])}
    np.testing.assert_allclose(a.evaluate('min(close, open)', p)[0], [1, 1, 2])
    assert a.evaluate('min(close, 3)', p).iloc[-1, 0] == 1
    assert a.evaluate('min(close, 3)', p).iloc[:2].isna().all().all()


def test_industry_group_demeaning_uses_historical_level_and_missing_groups():
    a = api()
    p = {'close': frame([[1, 3, 9], [1, 3, 9]]),
         'indclass.sector': pd.DataFrame([['a', 'a', 'b'], ['a', 'a', None]])}
    got = a.evaluate('indneutralize(close, IndClass.sector)', p)
    np.testing.assert_allclose(got.iloc[0], [-1, 1, 0])
    assert got.iloc[1].isna().all()


def test_all_supported_alphas_preserve_past_when_future_appended():
    a = api()
    rng = np.random.default_rng(731)
    p = {k: pd.DataFrame(rng.uniform(1, 100, (270, 4))) for k in ['open', 'close', 'high', 'low', 'vwap', 'volume', 'amount', 'cap']}
    p['returns'] = p['close'].pct_change(fill_method=None)
    for k in ['sector', 'industry', 'subindustry']:
        p['indclass.' + k] = pd.DataFrame(np.tile(['a', 'a', 'b', 'b'], (270, 1)))
    for row in a.dependency_matrix():
        full = a.compute(row['alpha_id'], p)
        partial = a.compute(row['alpha_id'], {k: v.iloc[:260] for k, v in p.items()})
        pd.testing.assert_frame_equal(full.iloc[:260], partial)
        assert not np.isinf(full.to_numpy()).any()
        assert full.iloc[:row['lookback_days'] - 1].isna().all().all()


def test_explicit_daily_universe_excludes_members_without_hiding_eligible_missing():
    a = api()
    p = {'close': frame([[1, 3, np.nan], [2, np.nan, 4], [3, 1, 5]]),
         'universe': pd.DataFrame([[True, True, False], [True, True, False], [True, True, True]])}
    got = a.evaluate('rank(close)', p)
    np.testing.assert_allclose(got.iloc[0, :2], [.5, 1])
    assert np.isnan(got.iloc[0, 2])
    assert got.iloc[1].isna().all()
    p = {'close': frame([[1, 2], [2, 3], [3, 4]]),
         'universe': pd.DataFrame([[True, False], [True, False], [True, True]])}
    assert a.evaluate('sum(close, 3)', p).iloc[-1, 1] == 9


def test_long_nested_adv_and_correlation_matches_independent_window_calculation():
    rng = np.random.default_rng(20260913)
    volume = frame(rng.uniform(10, 40, (240, 3)))
    vwap = frame(rng.uniform(2, 8, (240, 3)))
    # Last #61 correlation consumes 17 observations of ADV180: 196 bars total.
    got = api().compute(61, {'volume': volume, 'vwap': vwap}, adv_basis='volume')
    assert got.iloc[:195].isna().all().all()
    correlations = []
    for column in range(3):
        means = [np.mean(volume.iloc[t-179:t+1, column].to_numpy()) for t in range(223, 240)]
        correlations.append(np.corrcoef(vwap.iloc[-17:, column].to_numpy(), means)[0, 1])
    left = vwap.iloc[-1].to_numpy() - np.min(vwap.iloc[-16:].to_numpy(), axis=0)
    ranks = lambda values: np.array([sum(v < x for v in values) + (sum(v == x for v in values)+1)/2 for x in values]) / len(values)
    np.testing.assert_array_equal(got.iloc[-1], (ranks(left) < ranks(correlations)).astype(float))


def test_nested_window_exact_first_valid_and_no_future_backfill():
    values = frame([[i] for i in range(1, 21)])
    got = api().evaluate('sum(delta(sum(close, 4), 5), 3)', {'close': values})
    assert got.iloc[:10].isna().all().all()  # 4 + delay5 + sum2 = 11 bars
    assert got.iloc[10, 0] == 60  # each delta of a 4-value sum is 20, repeated 3
    values.iloc[9, 0] = np.nan
    changed = api().evaluate('sum(delta(sum(close, 4), 5), 3)', {'close': values})
    assert changed.iloc[10:20, 0].isna().all()


def test_tie_argextrema_covariance_power_and_log_conventions():
    a = api()
    p = {'close': frame([[3], [1], [3]]), 'volume': frame([[2], [3], [4]])}
    assert a.evaluate('ts_argmax(close, 3)', p).iloc[-1, 0] == 1
    assert a.evaluate('ts_rank(close, 3)', p).iloc[-1, 0] == pytest.approx(2.5/3)
    assert a.evaluate('covariance(close, volume, 3)', p).iloc[-1, 0] == pytest.approx(0)
    p = {'close': frame([[-2], [0], [2]])}
    np.testing.assert_allclose(a.evaluate('signedpower(close, 2)', p)[0], [4, 0, 4])
    assert a.evaluate('log(close)', p).iloc[:2].isna().all().all()


def test_basis_and_conventions_are_part_of_identity():
    amount = api().dependency_matrix()
    volume = api().dependency_matrix(adv_basis='volume')
    assert amount[60]['formula_hash'] != volume[60]['formula_hash']
    assert 'amount' in amount[60]['fields'] and 'volume' in volume[60]['fields']
    assert all(row['formula_status'] == 'IMPLEMENTED_UNQUALIFIED' for row in amount)
    assert all(row['evaluation_status'] == row['execution_status'] == row['strict_pit_status'] == 'NOT_ASSESSED' for row in amount)


def test_raw_alpha_mode_is_explicit_and_does_not_require_corporate_actions():
    result = api().compute(1, {'close': frame([[1], [2]]), 'returns': frame([[float('nan')], [1]])})
    assert result.attrs['alpha_family'] == 'WORLDQUANT_101'
    assert result.attrs['price_mode'] == 'RAW'
    assert result.attrs['corporate_action_mode'] == 'NONE'
    with pytest.raises(ValueError, match='price_mode'):
        api().compute(1, {'close': frame([[1], [2]]), 'returns': frame([[float('nan')], [1]])}, price_mode='mixed')


@pytest.mark.parametrize('alpha_id', [0, 102, True, 1.0, '1'])
def test_invalid_alpha_id(alpha_id):
    with pytest.raises(ValueError, match='alpha_id'):
        api().compute(alpha_id, {})


def test_invalid_date_order_and_universe_unknown_are_rejected():
    p = {'close': frame([[1], [2]])}
    p['close'].index = [1, 0]
    with pytest.raises(ValueError, match='sorted'):
        api().evaluate('rank(close)', p)
    p = {'close': frame([[1], [2]]), 'universe': frame([[1], [np.nan]])}
    with pytest.raises(ValueError, match='universe'):
        api().evaluate('rank(close)', p)
