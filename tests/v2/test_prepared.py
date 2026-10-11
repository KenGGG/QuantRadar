from unittest.mock import Mock
import json

import pandas as pd
import pytest

from quantradar2.prepared import FIELDS, PreparedProvider, prepare, requirements, load_snapshot
from quantradar2.frozen import FrozenDataError


class DataSource:
    def __init__(self):
        self.calls = 0
        self.calendar = pd.bdate_range('2023-01-01', '2024-03-15')
        self.frame = pd.DataFrame({c: 1.0 for c in FIELDS}, index=self.calendar)
        self.frame['paused'] = 0
        self.frame.index.name = 'time'

    def get_trade_days(self, start_date=None, end_date=None, count=None):
        self.calls += 1
        x = self.calendar
        if start_date: x = x[x >= pd.Timestamp(start_date)]
        if end_date: x = x[x <= pd.Timestamp(end_date)]
        return list(x[-count:] if count else x)

    def get_price(self, security, start_date=None, end_date=None, count=None, **kwargs):
        self.calls += 1
        x = self.frame
        if start_date: x = x.loc[x.index >= pd.Timestamp(start_date)]
        if end_date: x = x.loc[x.index <= pd.Timestamp(end_date)]
        return (x.tail(count) if count else x).copy()

    def get_security_info(self, security, date=None):
        self.calls += 1
        return {'code': security, 'query_date': date, 'start_date': '2023-01-01'}

    def get_split_dividend(self, *args):
        self.calls += 1
        return [{'date': '2024-01-03', 'security': '510300.XSHG', 'cash': 1.0}]


def build(tmp_path, source=None):
    source = source or DataSource()
    request = {'start_date': '2024-01-02', 'end_date': '2024-01-05',
               'reference_date': '2024-01-05', 'frequency': 'day', 'benchmark': None}
    plan = {'securities': ['510300.XSHG'], 'warmup_bars': 84}
    stats = prepare(source, request, plan, tmp_path/'run', tmp_path/'cache', {'engine': 'test'}, {'task': 'test'})
    return source, request, plan, stats, PreparedProvider(tmp_path/'run', {'task': 'test'})


def test_prepare_then_offline_slices_date_metadata_and_cache_reuse(tmp_path):
    source, request, plan, stats, local = build(tmp_path)
    expected = source.get_price('510300.XSHG', end_date='2024-01-03', count=84)
    calls = source.calls
    actual = local.get_price('510300.XSHG', end_date='2024-01-03', count=84, fields=FIELDS)
    pd.testing.assert_frame_equal(expected, actual, check_freq=False)
    assert actual.index.max() < pd.Timestamp('2024-01-04')
    assert local.get_security_info('510300.XSHG', '2024-01-02')['query_date'] == '2024-01-02'
    assert not local.get_split_dividend('510300.SH', '2024-01-04', '2024-01-05')
    assert local.get_split_dividend('510300.SH', '2024-01-02', '2024-01-03')[0]['security'] == '510300.SH'
    stats2 = prepare(source, request, plan, tmp_path/'run2', tmp_path/'cache', {'engine': 'test'}, {'task': 'other'})
    assert stats2['cache_hit'] and not stats['cache_hit']
    assert source.calls == calls
    assert load_snapshot(tmp_path/'run2', {'task': 'other'})[0] == local.dataset
    disconnected = Mock(side_effect=AssertionError('network must not be opened'))
    stats3 = prepare(disconnected, request, plan, tmp_path/'run3', tmp_path/'cache', {'engine': 'test'}, {})
    assert stats3['cache_hit']
    disconnected.assert_not_called()


def test_offline_failures_are_remembered_and_snapshot_integrity_checked(tmp_path):
    _, _, _, _, local = build(tmp_path)
    for invoke in [lambda: local.get_price('600519.XSHG'),
                   lambda: local.get_price('510300.XSHG', fields=['high_limit']),
                   lambda: local.get_price('510300.XSHG', end_date='2025-01-01'),
                   lambda: local.get_security_info('510300.XSHG', '2023-01-01'),
                   lambda: local.get_price('510300.XSHG', pre_factor_ref_date='2024-01-04'),
                   lambda: local.get_all_securities()]:
        with pytest.raises(FrozenDataError, match='network fallback forbidden'): invoke()
    assert len(local._connection.errors) == 6
    for invoke in [lambda: local.get_price('510300.XSHG', end_date='2023-01-01'),
                   lambda: local.get_trade_days(start_date='2025-01-01'),
                   lambda: local.get_trade_days(count=-1),
                   lambda: local.get_split_dividend('510300.XSHG', end_date='2023-01-01')]:
        with pytest.raises(FrozenDataError, match='network fallback forbidden'): invoke()
    with pytest.raises(FrozenDataError, match='identity mismatch'): PreparedProvider(tmp_path/'run', {})
    (tmp_path/'run'/'dataset.json').write_text('{}')
    with pytest.raises(FrozenDataError, match='checksum mismatch'): PreparedProvider(tmp_path/'run', {'task': 'test'})


def test_bulk_window_mismatch_never_publishes_cache(tmp_path):
    source = DataSource()
    original = source.get_price
    def changed(*args, **kwargs):
        frame = original(*args, **kwargs)
        if kwargs.get('count'): frame['close'] = 2.0
        return frame
    source.get_price = changed
    with pytest.raises(FrozenDataError, match='bulk/window semantics differ'): build(tmp_path, source)
    assert not list(tmp_path.rglob('dataset-manifest.json'))


def test_declaration_is_literal_and_validation_does_not_execute_strategy():
    assert requirements("DATA_REQUIREMENTS = {'securities': ['510300.XSHG'], 'warmup_bars': 84}\nraise RuntimeError()")['warmup_bars'] == 84
    with pytest.raises(ValueError): requirements('DATA_REQUIREMENTS = dict(securities=[])')
    with pytest.raises(ValueError): requirements('', {'securities': ['../x'], 'warmup_bars': 84})


def test_short_prelisting_history_remains_available_for_strategy_warmup(tmp_path):
    source = DataSource()
    source.frame = source.frame.loc[source.frame.index >= '2024-01-04']
    _, _, _, _, local = build(tmp_path, source)
    assert local.get_price('510300.XSHG', end_date='2024-01-03', count=84).empty
    assert len(local.get_price('510300.XSHG', end_date='2024-01-05', count=84)) == 2
    with pytest.raises(FrozenDataError, match='warmup'):
        local.get_price('510300.XSHG', end_date='2024-01-05', count=1000)


def test_native_reference_bar_must_be_present_in_requested_window(tmp_path):
    source = DataSource()
    original = source.get_price
    def anchored(*args, **kwargs):
        result = original(*args, **kwargs)
        reference = kwargs.get('pre_factor_ref_date')
        if reference and pd.Timestamp(reference) in result.index:
            result[['open','high','low','close']] *= 2
        return result
    source.get_price = anchored
    _, _, _, _, local = build(tmp_path, source)
    for cutoff in ['2024-01-03', '2024-01-05']:
        kwargs = {'end_date':cutoff,'count':2,'fields':FIELDS,'pre_factor_ref_date':'2024-01-05'}
        pd.testing.assert_frame_equal(source.get_price('510300.XSHG', **kwargs),
                                      local.get_price('510300.XSHG', **kwargs), check_freq=False)


def test_refresh_bypasses_shared_cache_without_changing_existing_task_snapshot(tmp_path):
    source, request, plan, _, local = build(tmp_path)
    old = (tmp_path/'run'/'dataset.json').read_bytes()
    calls = source.calls
    refreshed = prepare(source, dict(request,refresh_data=True), plan, tmp_path/'refreshed',
                        tmp_path/'cache', {'engine':'test'}, {'task':'refreshed'})
    assert not refreshed['cache_hit'] and source.calls > calls
    assert (tmp_path/'run'/'dataset.json').read_bytes() == old
