import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from quantradar2.storage import Store

@pytest.fixture
def store(tmp_path):
    return Store(tmp_path/"metadata.sqlite3")

def test_revision_and_run_inputs_stay_immutable(store):
    first=store.save_strategy("Example","x=1")
    run=store.create_run(first["revision_id"],{"frequency":"day"})
    second=store.save_strategy("Renamed","x=2",first["id"])
    assert second["revision"]==2
    assert store.revision(run["revision_id"])["source"]=="x=1"
    with pytest.raises(sqlite3.IntegrityError):
        with store.connection() as db:
            db.execute("UPDATE revisions SET source='bad' WHERE id=?",(first["revision_id"],))
    with pytest.raises(sqlite3.IntegrityError):
        with store.connection() as db:
            db.execute("UPDATE runs SET request_json='{}' WHERE id=?",(run["id"],))

def test_concurrent_claims_are_serialized_and_fifo(store):
    strategy=store.save_strategy("Example","x=1")
    first=store.create_run(strategy["revision_id"],{})
    second=store.create_run(strategy["revision_id"],{})
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims=list(pool.map(lambda _:store.claim_next(),range(4)))
    winners=[r for r in claims if r]
    assert len(winners)==1 and winners[0]["id"]==first["id"]
    store.transition(first["id"],"SUCCEEDED",exit_code=0)
    assert store.claim_next()["id"]==second["id"]

def test_cancelled_queue_and_terminal_runs_are_not_retried(store):
    strategy=store.save_strategy("Example","x=1")
    run=store.create_run(strategy["revision_id"],{})
    store.transition(run["id"],"CANCELLED")
    assert store.claim_next() is None
    with pytest.raises(ValueError):store.transition(run["id"],"RUNNING")
    reopened=Store(store.path)
    assert reopened.run(run["id"])["status"]=="CANCELLED"
    assert reopened.revision(strategy["revision_id"])["source"]=="x=1"

def test_newer_schema_is_not_overwritten(tmp_path):
    path=tmp_path/"metadata.sqlite3"
    with sqlite3.connect(path) as db:db.execute("PRAGMA user_version=99")
    with pytest.raises(ValueError,match="newer"):Store(path)
    with sqlite3.connect(path) as db:assert db.execute("PRAGMA user_version").fetchone()[0]==99

def test_v1_migration_retains_revisions_runs_and_archive_is_reversible(tmp_path):
    from quantradar2.storage import Store
    path=tmp_path/"metadata.sqlite3";store=Store(path)
    strategy=store.save_strategy("kept","pass")
    run=store.create_run(strategy["revision_id"],{"frequency":"day"})
    with store.connection() as db:
        db.execute("ALTER TABLE strategies DROP COLUMN archived")
        db.execute("PRAGMA user_version=1")
    migrated=Store(path)
    assert migrated.run(run["id"])["request"]=={"frequency":"day"}
    migrated.archive_strategy(strategy["id"])
    assert not migrated.strategies()
    assert len(migrated.strategies(True))==1
    assert migrated.revision(strategy["revision_id"])["source"]=="pass"
    migrated.archive_strategy(strategy["id"],False)
    assert migrated.strategies()[0]["id"]==strategy["id"]
