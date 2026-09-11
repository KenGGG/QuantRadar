from __future__ import annotations

import socket
import subprocess
import time

import pymysql
import pytest


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_dolt(port: int) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            connection = pymysql.connect(host="127.0.0.1", port=port, user="root", database="quantradar_data")
            connection.close()
            return
        except pymysql.MySQLError:
            time.sleep(0.1)
    raise AssertionError("temporary Dolt SQL server did not become ready")


@pytest.mark.requires_dolt
def test_old_release_queries_its_original_supplemental_dolt_commit(tmp_path):
    from quantradar.config import DataHubConfig
    from quantradar.datahub.dolt import SupplementalStore
    from quantradar.datahub.reader import ReleaseReader
    from quantradar.datahub.release import ReleaseStore

    data_dir = tmp_path / "databases"
    repo = data_dir / "quantradar_data"
    repo.mkdir(parents=True)
    subprocess.run(["dolt", "init"], cwd=repo, check=True, capture_output=True, text=True)
    port = _port()
    process = subprocess.Popen(
        ["dolt", "sql-server", "--data-dir", str(data_dir), "-H", "127.0.0.1", "-P", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_dolt(port)
        connection = pymysql.connect(host="127.0.0.1", port=port, user="root", database="quantradar_data", cursorclass=pymysql.cursors.DictCursor)
        store = SupplementalStore(connection)
        store.ensure_schema()
        first = {"trade_date": "2016-01-04", "symbol": "600005.SH", "pe_ttm": 1.0, "pb_mrq": 1.0, "ps_ttm": 1.0, "pcf_ncf_ttm": 1.0,
                 "source": "test", "raw_sha256": "a" * 64, "adapter_version": "test", "fetched_at": "2026-09-09T00:00:00+00:00", "available_date": None, "pit_status": "PARTIAL"}
        store.upsert_valuations([first])
        commit_one = store.commit("first supplemental value")
        store.upsert_valuations([{**first, 'fetched_at': '2026-09-11T00:00:00+00:00'}])
        with connection.cursor() as cursor:
            cursor.execute('SELECT * FROM dolt_status')
            assert not cursor.fetchall()
        releases = ReleaseStore(tmp_path / "releases")
        release_one = releases.publish(base_commit="base-1", supplemental_commit=commit_one, datasets={}, source_adapters={})

        second = dict(first, pb_mrq=9.0, raw_sha256="b" * 64)
        store.upsert_valuations([second])
        commit_two = store.commit("second supplemental value")
        release_two = releases.publish(base_commit="base-2", supplemental_commit=commit_two, datasets={}, source_adapters={})
        connection.close()

        reader = ReleaseReader(DataHubConfig(release_root=str(tmp_path / "releases"), supplemental_port=port))
        old_value = reader.supplemental_reader(reader.resolve(release_one["release_id"])).valuation("600005.SH", "2016-01-04", "2016-01-04")["rows"][0]["pb_mrq"]
        new_value = reader.supplemental_reader(reader.resolve(release_two["release_id"])).valuation("600005.SH", "2016-01-04", "2016-01-04")["rows"][0]["pb_mrq"]
        assert old_value == 1.0
        assert new_value == 9.0
    finally:
        process.terminate()
        process.wait(timeout=10)


@pytest.mark.requires_dolt
def test_checked_partial_publication_and_economic_idempotency(tmp_path):
    import json
    import hashlib
    from types import SimpleNamespace
    from quantradar.datahub.publication import publish_candidate
    from quantradar.datahub.quality import validate_candidate
    from quantradar.datahub.release import ReleaseStore
    repo = tmp_path / 'quantradar_data'
    repo.mkdir()
    subprocess.run(['dolt', 'init'], cwd=repo, check=True, capture_output=True)
    port = _port()
    process = subprocess.Popen(['dolt', 'sql-server', '--data-dir', str(tmp_path), '-H', '127.0.0.1', '-P', str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        _wait_for_dolt(port)
        stage = repo / 'staging' / 'valuation_daily-mvp' / 'valuation_daily'
        stage.mkdir(parents=True)
        provenance = {'source': 'eastmoney:RPT_VALUEANALYSIS_DET', 'raw_sha256': 'a'*64, 'adapter_version': 'test', 'fetched_at': '2026-09-11', 'available_date': None, 'pit_status': 'PARTIAL'}
        row = {**provenance, 'symbol': '600519.SH', 'trade_date': '2026-09-10', 'pe_ttm': 10, 'pb_mrq': 2, 'ps_ttm': 3, 'pcf_ocf_ttm': 4}
        content = (json.dumps(row) + '\n').encode()
        (stage / '600519.SH.jsonl').write_bytes(content)
        units = {'600519.SH': {'status': 'COMPLETE', 'row_count': 1, 'staged_result_sha256': hashlib.sha256(content).hexdigest()}, '000001.SZ': {'status': 'FAILED'}}
        candidate = validate_candidate(stage.parent, units, base_commit='fixed-base')
        def connect(database=None):
            return pymysql.connect(host='127.0.0.1', port=port, user='root', database=database or 'quantradar_data', cursorclass=pymysql.cursors.DictCursor)
        service = SimpleNamespace(config=SimpleNamespace(supplemental_repo=str(repo), supplemental_database='quantradar_data'), releases=ReleaseStore(tmp_path/'releases'), _connection=connect,
            _existing_industries=lambda: [], _base_lifecycle=lambda **_: [{**provenance, 'source': 'investment_data:ts_a_stock_list:BASE_EXISTING', 'symbol': '600519.SH', 'list_date': '2001-08-27', 'delist_date': None, 'status': 'LISTED'}])
        published = publish_candidate(service, candidate)
        assert published['status'] == 'PARTIAL'
        manifest = service.releases.current()
        assert manifest['datasets']['valuation_daily']['row_count'] == 1
        assert '000001.SZ' in manifest['metadata']['isolated']
        assert publish_candidate(service, candidate)['status'] == 'NO_CHANGE'
        with connect('quantradar_data/' + published['supplemental_commit']) as conn, conn.cursor() as cur:
            cur.execute('SELECT pe_ttm FROM qr_valuation_daily')
            assert cur.fetchone()['pe_ttm'] == 10
    finally:
        process.terminate()
        process.wait(timeout=10)
