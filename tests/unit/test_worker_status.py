"""Worker terminal states must not retain recovery messages as errors."""


def test_successful_recovered_run_clears_previous_error(monkeypatch):
    from quantradar.worker import BacktestWorker

    updates = []
    info = {
        "snapshot": {"snapshot_id": "snapshot", "value": 1},
        "result_hash": "result",
        "metrics": {"return": 1},
    }
    monkeypatch.setattr("quantradar.worker.run_unified_backtest", lambda *_: info)
    monkeypatch.setattr("quantradar.worker.save_snapshot_record", lambda *_: None)
    monkeypatch.setattr("quantradar.worker.save_metrics", lambda *_: None)
    monkeypatch.setattr("quantradar.worker.update_run", lambda run_id, **fields: updates.append(fields))

    BacktestWorker()._run("run_recovered", {})

    assert updates[-1]["status"] == "SUCCESS"
    assert updates[-1]["error"] is None
