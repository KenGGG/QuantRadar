import json,hashlib,os
from unittest.mock import patch
import psutil
from quantradar2.manager import Manager
from quantradar2.runtime import Runtime
from quantradar2.storage import Store

def setup(tmp_path):
    store=Store(tmp_path/"metadata.sqlite3")
    strategy=store.save_strategy("sample","pass")
    run=store.create_run(strategy["revision_id"],{})
    return store,Manager(store,Runtime(tmp_path,tmp_path/"data.env")),run

def test_restart_marks_running_interrupted_and_never_kills_reused_pid(tmp_path):
    store,manager,run=setup(tmp_path)
    store.claim_next()
    store.transition(run["id"],"RUNNING",pid=os.getpid(),process_created=psutil.Process().create_time()+10)
    with patch.object(psutil.Process,"terminate") as terminate:
        manager.start();manager.close()
        terminate.assert_not_called()
    assert store.run(run["id"])["status"]=="INTERRUPTED"
    assert store.claim_next() is None

def test_restart_recovers_valid_completion_without_reexecution(tmp_path):
    store,manager,run=setup(tmp_path);store.claim_next()
    directory=tmp_path/"runs"/run["id"];directory.mkdir(parents=True)
    content=b"test report";(directory/"report.html").write_bytes(content)
    (directory/"completion.json").write_text(json.dumps({"status":"SUCCEEDED","artifacts":[{"name":"report.html","sha256":hashlib.sha256(content).hexdigest(),"bytes":len(content)}]}))
    with patch.object(manager,"launch") as launch:
        manager.start();manager.close();launch.assert_not_called()
    assert store.run(run["id"])["status"]=="SUCCEEDED"
    assert store.artifacts(run["id"])[0]["name"]=="report.html"

def test_completion_checksum_mismatch_fails_closed(tmp_path):
    store,manager,run=setup(tmp_path);store.claim_next()
    directory=tmp_path/"runs"/run["id"];directory.mkdir(parents=True)
    (directory/"report.html").write_text("changed")
    (directory/"completion.json").write_text(json.dumps({"status":"SUCCEEDED","artifacts":[{"name":"report.html","sha256":"bad","bytes":7}]}))
    manager.start();manager.close()
    assert store.run(run["id"])["status"]=="FAILED"
    assert not store.artifacts(run["id"])

def test_restart_uses_verified_runner_marker_before_pid_database_update(tmp_path):
    store,manager,run=setup(tmp_path);store.claim_next()
    directory=tmp_path/"runs"/run["id"];directory.mkdir(parents=True)
    (directory/"runner-process.json").write_text(json.dumps({"pid":424242,"process_created":123.0}))
    with patch.object(manager,"owned",side_effect=lambda r:object() if r.get("pid")==424242 else None),patch.object(manager,"terminate") as terminate:
        manager.start();manager.close()
        assert terminate.call_args.args[0]["pid"]==424242
    recovered=store.run(run["id"])
    assert recovered["status"]=="INTERRUPTED" and recovered["pid"]==424242
