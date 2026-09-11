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
