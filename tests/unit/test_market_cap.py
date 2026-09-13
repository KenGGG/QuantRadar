from quantradar.datahub.market_cap import parse_eastmoney_market_cap


def test_parser_uses_total_not_float_market_cap():
    rows = parse_eastmoney_market_cap('数据日期,总市值,流通市值\n2020-01-02,100,50\n'.encode(), symbol='000001.SZ', raw_sha256='a'*64)
    assert rows == [{'trade_date':'2020-01-02','symbol':'000001.SZ','total_market_cap_cny':100.0,
                     'source':'eastmoney:RPT_VALUEANALYSIS_DET','raw_sha256':'a'*64,'pit_status':'PARTIAL','qualification':'CANDIDATE_NOT_PUBLISHED'}]


def test_market_cap_candidate_requires_total_cap_and_archived_provenance():
    from quantradar.datahub.market_cap import validate_market_cap_candidate

    row = parse_eastmoney_market_cap(
        '数据日期,总市值\n2020-01-02,100\n'.encode(), symbol='000001.SZ', raw_sha256='a' * 64
    )[0]
    assert validate_market_cap_candidate([row]) == {'status': 'PASS', 'rows': 1, 'errors': []}

    broken = {**row, 'total_market_cap_cny': None}
    assert validate_market_cap_candidate([broken]) == {
        'status': 'FAIL', 'rows': 1, 'errors': ['invalid total market cap']
    }


def test_fixed_supplemental_reader_returns_published_total_market_cap():
    from quantradar.datahub.reader import SupplementalReader

    reader = SupplementalReader(lambda: None)
    reader._query = lambda sql, args: [{
        'trade_date': '2020-01-02', 'total_market_cap_cny': 100.0, 'pit_status': 'PARTIAL'
    }]
    assert reader.market_cap('000001.SZ', '2020-01-02', '2020-01-02') == {
        'rows': [{'trade_date': '2020-01-02', 'total_market_cap_cny': 100.0, 'pit_status': 'PARTIAL'}],
        'pit_status': 'PARTIAL',
    }


def test_catalog_materializer_rechecks_archived_hash_and_adds_ingestion_provenance(tmp_path):
    import hashlib
    from quantradar.datahub.market_cap import materialize_market_cap_catalog

    raw = '数据日期,总市值\n2020-01-02,100\n'.encode()
    digest = hashlib.sha256(raw).hexdigest()
    raw_root = tmp_path / 'raw'
    raw_root.mkdir()
    (raw_root / digest).write_bytes(raw)
    catalog = {'artifacts': [{'kind': 'PARSED_SNAPSHOT', 'source': 'eastmoney:RPT_VALUEANALYSIS_DET',
                              'symbol': '000001.SZ', 'sha256': digest}]}

    rows = list(materialize_market_cap_catalog(catalog, raw_root=raw_root, fetched_at='2026-09-13T00:00:00Z'))
    assert rows == [{
        'trade_date': '2020-01-02', 'symbol': '000001.SZ', 'total_market_cap_cny': 100.0,
        'source': 'eastmoney:RPT_VALUEANALYSIS_DET', 'raw_sha256': digest,
        'pit_status': 'PARTIAL', 'qualification': 'CANDIDATE_NOT_PUBLISHED',
        'adapter_version': 'eastmoney-archive-v1', 'fetched_at': '2026-09-13T00:00:00Z', 'available_date': None,
    }]


def test_market_cap_delta_rejects_rewrite_of_an_already_published_observation():
    from quantradar.datahub.publication import market_cap_patch_delta

    row = {'trade_date': '2020-01-02', 'symbol': '000001.SZ', 'total_market_cap_cny': 100.0,
           'raw_sha256': 'a' * 64, 'qualification': 'CANDIDATE_NOT_PUBLISHED'}
    assert market_cap_patch_delta([row], {}) == {'new_rows': [row], 'conflicts': []}
    assert market_cap_patch_delta([{**row, 'total_market_cap_cny': 101.0}], {
        ('2020-01-02', '000001.SZ'): row
    }) == {'new_rows': [], 'conflicts': [('2020-01-02', '000001.SZ')]}


def test_fixed_supplemental_reader_groups_market_cap_for_a_research_panel():
    from quantradar.datahub.reader import SupplementalReader

    reader = SupplementalReader(lambda: None)
    reader._query = lambda sql, args: [
        {'symbol': '000001.SZ', 'trade_date': '2020-01-02', 'total_market_cap_cny': 100.0, 'pit_status': 'PARTIAL'},
        {'symbol': '600000.SH', 'trade_date': '2020-01-02', 'total_market_cap_cny': 200.0, 'pit_status': 'PARTIAL'},
    ]
    assert reader.market_caps(['000001.SZ', '600000.SH'], '2020-01-02', '2020-01-02') == {
        '000001.SZ': [{'symbol': '000001.SZ', 'trade_date': '2020-01-02', 'total_market_cap_cny': 100.0, 'pit_status': 'PARTIAL'}],
        '600000.SH': [{'symbol': '600000.SH', 'trade_date': '2020-01-02', 'total_market_cap_cny': 200.0, 'pit_status': 'PARTIAL'}],
    }
