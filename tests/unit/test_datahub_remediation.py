import json
import pytest
from quantradar.datahub.store import UpdateJournal
from quantradar.datahub.mvp import ShardRunner


def test_concurrent_control_is_not_lost_to_stale_writer(tmp_path):
    worker = UpdateJournal(tmp_path / 'journal.json')
    worker.fail('bad', 'failure')
    control = UpdateJournal(worker.path)
    control.request_pause()
    worker.heartbeat(phase='download', current_shard='bad', pid=1)
    assert UpdateJournal(worker.path).paused()
    control.set_total_shards(3)
    assert UpdateJournal(worker.path).data['heartbeat']['current_shard'] == 'bad'


@pytest.mark.parametrize('response', [None, []])
def test_unknown_empty_is_isolated(tmp_path, response):
    journal = UpdateJournal(tmp_path / 'journal.json')
    ShardRunner(tmp_path, journal, lambda _: response).run(['600000.SH'])
    assert journal.data['units']['600000.SH']['category'] == 'UNKNOWN_EMPTY'
    assert journal.data['units']['600000.SH']['status'] == 'FAILED'


def test_cooldown_expiry_can_be_observed_without_writing(tmp_path):
    from quantradar.datahub.governor import RequestGovernor
    governor = RequestGovernor(tmp_path, 'eastmoney')
    content = json.dumps({'circuit_open': True, 'cooldown_until': '2000-01-01T00:00:00+00:00'})
    governor.path.write_text(content)
    assert governor.observed_status()['probe_due']
    assert not governor.observed_status()['circuit_open']
    assert governor.path.read_text() == content


def test_candidate_rejects_duplicate_and_tampered_input(tmp_path):
    import hashlib
    from quantradar.datahub.quality import validate_shard
    row = {'symbol': '600000.SH', 'trade_date': '2026-09-10', 'source': 'eastmoney:RPT_VALUEANALYSIS_DET',
           'pit_status': 'PARTIAL', 'adapter_version': 'test', 'raw_sha256': 'a' * 64,
           'pe_ttm': -1, 'pb_mrq': None, 'ps_ttm': 3, 'pcf_ocf_ttm': 4}
    content = (json.dumps(row) + '\n').encode()
    path = tmp_path / 'shard.jsonl'
    path.write_bytes(content)
    unit = {'row_count': 1, 'staged_result_sha256': hashlib.sha256(content).hexdigest()}
    assert validate_shard(path, '600000.SH', unit)['status'] == 'PASS'
    path.write_bytes(content * 2)
    result = validate_shard(path, '600000.SH', unit)
    assert result['errors']['duplicate_key'] == 1
    assert result['errors']['content_hash'] == 1


def test_candidate_detects_internal_missing_day(tmp_path):
    import hashlib
    from quantradar.datahub.quality import validate_candidate
    path = tmp_path / 'valuation_daily'
    path.mkdir()
    rows = [{'symbol': '600000.SH', 'trade_date': day, 'source': 'eastmoney:RPT_VALUEANALYSIS_DET', 'pit_status': 'PARTIAL', 'adapter_version': 'test', 'raw_sha256': 'a' * 64, 'pe_ttm': 1, 'pb_mrq': 2, 'ps_ttm': 3, 'pcf_ocf_ttm': 4} for day in ('2026-09-08', '2026-09-10')]
    content = ''.join(json.dumps(row) + '\n' for row in rows).encode()
    (path / '600000.SH.jsonl').write_bytes(content)
    report = validate_candidate(tmp_path, {'600000.SH': {'status': 'COMPLETE', 'row_count': 2, 'staged_result_sha256': hashlib.sha256(content).hexdigest()}}, base_commit='base', calendar=['2026-09-08', '2026-09-09', '2026-09-10'])
    assert report['shards']['600000.SH']['missing_internal_days'] == 1


def test_strategy_bridge_checks_requested_universe_before_filtering():
    from types import SimpleNamespace
    import jqdatasdk as jq
    from quantradar.datahub.strategy import fundamentals, DataUnavailable
    queries = []
    def read(sql, params):
        queries.append((sql, params))
        if 'SELECT symbol,' in sql:
            return [{'symbol': '600519.SH', 'pe_ttm': 10, 'pb_mrq': 2, 'ps_ttm': 3, 'pit_status': 'PARTIAL'}]
        return [{'code': '600519.XSHG', 'pe_ratio': 10}]
    provider = SimpleNamespace(_supplemental_reader=SimpleNamespace(_query=read),
                              _release_scope=SimpleNamespace(manifest={}, release_id='R-test'),
                              get_trade_days=lambda **_: ['2026-09-10'])
    q = jq.query(jq.valuation.code, jq.valuation.pe_ratio).filter(jq.valuation.code.in_(['600519.XSHG']))
    result = fundamentals(provider, q, '2026-09-10')
    assert result.iloc[0]['pe_ratio'] == 10
    assert result.attrs['release_id'] == 'R-test'
    assert 'qr_valuation_daily' in queries[-1][0]
    assert queries[-1][1] == ('2026-09-10', '600519.XSHG')
    missing = jq.query(jq.valuation.code).filter(jq.valuation.code.in_(['600519.XSHG', '000001.XSHE']))
    with pytest.raises(DataUnavailable, match='000001.SZ'):
        fundamentals(provider, missing, '2026-09-10')
    with pytest.raises(DataUnavailable, match='明确'):
        fundamentals(provider, jq.query(jq.valuation.code), '2026-09-10')


def test_base_only_release_does_not_fabricate_supplemental_commit(tmp_path):
    from quantradar.datahub.release import ReleaseStore
    from quantradar.datahub.reader import ReleaseReader
    from quantradar.config import DataHubConfig
    store = ReleaseStore(tmp_path)
    manifest = store.publish(base_commit='base', supplemental_commit=None, datasets={}, source_adapters={})
    reader = ReleaseReader(DataHubConfig(release_root=str(tmp_path)))
    scope = reader.resolve(manifest['release_id'])
    assert scope.supplemental_database is None
    with pytest.raises(ValueError, match='仅提供基础行情'):
        reader.supplemental_reader(scope)


def test_deterministic_same_version_repair_does_not_repeat_requests(tmp_path):
    journal = UpdateJournal(tmp_path / 'journal.json')
    journal.fail('600000.SH', 'NoneType', category='SYMBOL_DATA_ERROR', adapter_version='akshare-1.18.94')
    runner = ShardRunner(tmp_path, journal, lambda _: pytest.fail('must not request source'))
    result = runner.repair_failed()
    assert result['failed'] == 1
    assert result['skipped_same_adapter'] == 1


def test_maintenance_cannot_interrupt_a_backtest_read_lease():
    from quantradar.datahub.maintenance import base_lease
    with base_lease():
        with pytest.raises(RuntimeError, match='回测'):
            with base_lease(exclusive=True):
                pytest.fail('exclusive maintenance overlapped a read lease')


def test_sync_watermark_checks_revisions_once_per_target_and_backfill_checks_holes():
    from quantradar.datahub.daily import plan_symbols
    units = {'600000.SH': {'status': 'COMPLETE', 'first_date': '2020-01-01', 'last_date': '2026-09-10'}}
    assert plan_symbols(units, {}, '2026-09-10') == ['600000.SH']
    units['600000.SH']['last_checked_target'] = '2026-09-10'
    assert plan_symbols(units, {}, '2026-09-10') == []
    assert plan_symbols(units, {}, '2026-09-11') == ['600000.SH']
    assert plan_symbols(units, {}, '2026-09-10', mode='backfill', start='2026-09-01', summaries={'600000.SH': {'missing_internal_days': 1}}) == ['600000.SH']


def test_daily_target_is_limited_by_observed_price_coverage():
    from quantradar.datahub.daily import latest_complete_target

    assert latest_complete_target(['2026-09-11', '2026-09-14', '2026-09-15'], '2026-09-15', '2026-09-14') == '2026-09-14'


def test_non_object_candidate_row_is_isolated(tmp_path):
    import hashlib
    from quantradar.datahub.quality import validate_shard
    path = tmp_path / 'invalid.jsonl'
    content = b'[]\n'
    path.write_bytes(content)
    result = validate_shard(path, '600000.SH', {'row_count': 1, 'staged_result_sha256': hashlib.sha256(content).hexdigest()})
    assert result['status'] == 'FAIL'
    assert result['errors']['row_type'] == 1


def test_provider_database_errors_cannot_be_swallowed_as_an_empty_universe(monkeypatch):
    from quantradar.datahub import strategy
    from quantradar.providers.investment_data.provider import InvestmentDataProvider
    def broken(*args):
        raise ConnectionError('database unavailable')
    monkeypatch.setattr(strategy, 'fundamentals', broken)
    with pytest.raises(strategy.DataUnavailable, match='database unavailable'):
        InvestmentDataProvider.get_fundamentals(object(), object())


def test_daily_double_click_reserves_only_one_process(tmp_path, monkeypatch):
    import os
    from types import SimpleNamespace
    from quantradar.datahub.daily import DailyUpdate
    from quantradar.datahub import daily
    launches = []
    def launch(*args, **kwargs):
        launches.append(args)
        return SimpleNamespace(pid=os.getpid())
    monkeypatch.setattr(daily.subprocess, 'Popen', launch)
    service = SimpleNamespace(config=SimpleNamespace(supplemental_repo=str(tmp_path)), job_status=lambda: {'worker_alive': False})
    update = DailyUpdate(service)
    assert update.start()['status'] == 'RUNNING'
    assert update.start()['status'] == 'ALREADY_RUNNING'
    assert len(launches) == 1
    with pytest.raises(ValueError, match='backfill'):
        update.start('sync', start='2026-09-01')


def test_status_maintenance_processes_a_bounded_current_window_batch():
    from quantradar.datahub.daily import CURRENT_STATUS_TASK_LIMIT

    assert CURRENT_STATUS_TASK_LIMIT == 50


def test_cli_does_not_silently_ignore_unsupported_dataset(capsys):
    from quantradar.datahub.cli import main
    assert main(['sync', '--dataset', 'sw_industry_history']) == 1
    assert '没有已验收' in capsys.readouterr().out


def test_etf_trading_rule_publish_is_idempotent_when_candidate_already_exists(tmp_path, monkeypatch):
    """A release retry must reuse the existing branch head when Dolt is clean."""
    from types import SimpleNamespace
    from quantradar.datahub import publication

    symbols = ['510050.SH', '510180.SH', '510300.SH', '510500.SH', '510880.SH',
               '159901.SZ', '159902.SZ', '159903.SZ', '159915.SZ', '159919.SZ']
    rows = [
        {'symbol': symbol, 'exchange': 'SSE' if symbol.endswith('.SH') else 'SZSE',
         'effective_from': '2026-07-06', 'available_at': '2026-04-24',
         'lot_size': 100, 'tick_size': .001, 'turnover_status': 'UNKNOWN',
         'fee_status': 'UNKNOWN', 'special_status': 'UNKNOWN',
         'rule_scope': 'EXCHANGE_FUND_RULE', 'qualification': 'EXCHANGE_RULE_PARTIAL',
         'raw_sha256': 'a' * 64, 'source': 'exchange-rule'}
        for symbol in symbols
    ]
    stage = tmp_path / 'rules.jsonl'
    stage.write_text(''.join(json.dumps(row) + '\n' for row in rows))

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, sql, args=None): self.sql = sql
        def fetchall(self): return []
        def fetchone(self):
            if 'dolt_branches' in self.sql: return None
            if 'dolt_log' in self.sql: return {'commit_hash': 'existing-commit'}
            return None

    class Connection:
        def cursor(self): return Cursor()
        def close(self): pass

    committed = []
    class Store:
        def __init__(self, connection): pass
        def ensure_schema(self): pass
        def upsert_etf_trading_rules(self, values): assert list(values) == rows
        def commit(self, message): committed.append(message); return 'unexpected-commit'

    monkeypatch.setattr(publication, 'SupplementalStore', Store)
    old = {'base_commit': 'base', 'supplemental_commit': 'prior', 'datasets': {}, 'source_adapters': {}, 'metadata': {}}
    service = SimpleNamespace(
        releases=SimpleNamespace(current=lambda: old, publish=lambda **kwargs: {'release_id': 'R-test'}),
        _connection=lambda *args: Connection(),
    )
    result = publication.publish_etf_trading_rule_stage(service, stage)
    assert committed == []
    assert result['supplemental_commit'] == 'existing-commit'


def test_new_units_are_converted_once_and_legacy_release_units_are_preserved(monkeypatch):
    import pandas as pd
    from quantradar.providers.investment_data.provider import InvestmentDataProvider
    provider = InvestmentDataProvider()
    raw = pd.DataFrame({'volume': [2.5], 'amount': [12.4]}, index=pd.to_datetime(['2023-09-08']))
    monkeypatch.setattr(provider, '_fetch_raw_price', lambda *args, **kwargs: raw)
    for _ in range(2):
        frame = provider.get_price('600519.XSHG', '2023-09-08', '2023-09-08', fields=['volume', 'money'])
        assert frame.iloc[0].to_dict() == {'volume': 250, 'money': 12400}
    assert raw.iloc[0].to_dict() == {'volume': 2.5, 'amount': 12.4}
    provider._price_units = 'legacy-v1'
    frame = provider.get_price('600519.XSHG', '2023-09-08', '2023-09-08', fields=['volume', 'money'])
    assert frame.iloc[0].to_dict() == {'volume': 2.5, 'money': 12.4}


def test_release_pinned_etf_raw_prices_keep_native_share_and_yuan_units(monkeypatch):
    import pandas as pd
    from types import SimpleNamespace
    from quantradar.providers.investment_data.provider import InvestmentDataProvider

    class Reader:
        def etf_master(self, symbols):
            return {symbol: {'symbol': symbol} for symbol in symbols}

        def etf_prices(self, symbols, start, end):
            return {
                '510300.SH': [{
                    'symbol': '510300.SH', 'trade_date': '2024-01-02',
                    'open': 3.4, 'high': 3.5, 'low': 3.3, 'close': 3.45,
                    'volume_shares': 10000.0, 'amount_cny': 34500.0,
                    'pit_status': 'PARTIAL',
                }],
            }

    provider = InvestmentDataProvider()
    provider._release_scope = SimpleNamespace(manifest={'datasets': {'etf_eod_price': {}}})
    provider._supplemental_reader = Reader()
    monkeypatch.setattr(provider, 'get_trade_days', lambda start, end: [pd.Timestamp('2024-01-02')])
    monkeypatch.setattr(provider, '_fetch_raw_price', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('ETF must not query stock tables')))

    frame = provider.get_price('510300.XSHG', '2024-01-02', '2024-01-02', fields=['volume', 'money'])
    assert frame.iloc[0].to_dict() == {'volume': 10000.0, 'money': 34500.0}


def test_release_pinned_etf_master_is_available_to_the_backtest_engine():
    from types import SimpleNamespace
    from quantradar.providers.investment_data.provider import InvestmentDataProvider

    class Reader:
        def etf_master(self, symbols):
            return {'510300.SH': {
                'symbol': '510300.SH', 'fund_name': '沪深300ETF', 'exchange': 'SSE',
                'listing_date': '2012-05-28', 'termination_date': None,
            }}

    provider = InvestmentDataProvider()
    provider._release_scope = SimpleNamespace(manifest={'datasets': {'etf_master': {}}})
    provider._supplemental_reader = Reader()
    info = provider.get_security_info('510300.XSHG')
    assert info['type'] == 'fund'
    assert info['name'] == '沪深300ETF'
    assert str(info['start_date'].date()) == '2012-05-28'


def test_datahub_overview_qualification_keeps_etf_strict_account_closed():
    from quantradar.api.app import _research_qualification

    qualification = _research_qualification({'datasets': {
        'etf_eod_price': {'rows': 1}, 'etf_master': {'rows': 1},
        'sw_industry_history': {'industry_code_levels': ['L1', 'L2', 'L3']},
    }})
    assert qualification['etf']['ETF_RAW'] == 'READY'
    assert qualification['etf']['ACCOUNT_STRICT'] == 'BLOCKED'
    assert qualification['alpha101']['industry_hierarchy'] == 'PIT_PARTIAL'


def test_etf_raw_provider_refuses_unpublished_adjusted_modes(monkeypatch):
    from types import SimpleNamespace
    from quantradar.providers.investment_data.provider import InvestmentDataProvider

    class Reader:
        def etf_master(self, symbols):
            return {symbol: {'symbol': symbol} for symbol in symbols}

    provider = InvestmentDataProvider()
    provider._release_scope = SimpleNamespace(manifest={'datasets': {'etf_eod_price': {}}})
    provider._supplemental_reader = Reader()
    with pytest.raises(NotImplementedError, match='ETF_RAW'):
        provider.get_price('510300.XSHG', '2024-01-02', '2024-01-02', fq='hfq')
