from quantradar.datahub import research_inventory as inv


def test_gap_runs_preserve_missing_fields_and_denominator():
    days = ['2020-01-02', '2020-01-03', '2020-01-06']
    rows = {'2020-01-02': {'close': 10, 'volume': 100}, '2020-01-03': {'close': 11, 'volume': None}}
    result = inv.field_gap_runs('600000.SH', days, ['close', 'volume'], rows, purpose='formation')
    assert sum(r['key_count'] for r in result) == 6
    assert [(r['field'], r['action'], r['key_count']) for r in result] == [
        ('close', 'REUSE', 2), ('close', 'FETCH', 1),
        ('volume', 'REUSE', 1), ('volume', 'FETCH', 2)]


def test_prelisting_requires_evidence_and_unknown_not_zero():
    days = ['2020-01-02', '2020-01-03']
    unknown = inv.field_gap_runs('510300.SH', days, ['close'], {}, purpose='execution')
    assert unknown[0]['action'] == 'FETCH'
    known = inv.field_gap_runs('510300.SH', days, ['close'], {}, purpose='execution', listing_date='2020-01-03', lifecycle_evidence='a'*64)
    assert [r['action'] for r in known] == ['NOT_APPLICABLE', 'FETCH']
    import pytest
    with pytest.raises(ValueError, match='evidence'):
        inv.field_gap_runs('510300.SH', days, ['close'], {}, purpose='execution', listing_date='2020-01-03')


def test_raw_can_fill_only_missing_published_fields_and_finite_values():
    import math
    days=['2020-01-02','2020-01-03','2020-01-06']
    result=inv.field_gap_runs('600000.SH',days,['close'],{'2020-01-02':{'close':10},'2020-01-03':{'close':math.inf}},purpose='formation',raw_rows={'2020-01-02':{'close':12},'2020-01-03':{'close':11}})
    assert [r['action'] for r in result] == ['REUSE','REPARSE_RAW','FETCH']


def test_snapshot_future_and_staleness_are_not_silent_membership():
    import pytest
    snaps={'2020-01-02':['600000.SH'],'2020-02-03':['000001.SZ']}
    assert inv.snapshot_members(snaps,'2019-12-31',max_age_days=40)['status']=='UNKNOWN'
    assert inv.snapshot_members(snaps,'2020-02-04',max_age_days=40)['symbols']==['000001.SZ']
    r=inv.snapshot_members(snaps,'2021-01-04',max_age_days=40)
    assert r['status']=='STALE' and r['symbols']==['000001.SZ']
    assert r['strict_pit_ready'] is False


def test_nested_formation_and_label_execution_dependencies_keep_candidates():
    days=['2020-01-02','2020-01-03','2020-01-06','2020-01-07','2020-01-08']
    r=inv.research_dependencies(days, {'2020-01-06':['A','B']}, lookback_bars=3, label_sessions=2)
    assert r['formation']=={'A':days[:3],'B':days[:3]}
    assert r['execution']=={'A':[days[3]],'B':[days[3]]}
    assert r['label']=={'A':days[3:],'B':days[3:]}
    assert r['boundary_errors']==[]
    short=inv.research_dependencies(days, {'2020-01-02':['A'],'2020-01-08':['B']},lookback_bars=3,label_sessions=2)
    assert len(short['boundary_errors'])==3
