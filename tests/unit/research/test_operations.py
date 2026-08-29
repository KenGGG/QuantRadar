def test_runtime_lock_rejects_a_second_owner(tmp_path) -> None:
    from quantradar.research.operations import ResearchRunLock

    first = ResearchRunLock(tmp_path / "research.lock")
    second = ResearchRunLock(tmp_path / "research.lock")

    with first:
        assert second.acquire(blocking=False) is False
    assert second.acquire(blocking=False) is True
    second.release()


def test_operation_record_is_written_as_json_without_secrets(tmp_path) -> None:
    from quantradar.research.operations import write_operation_record

    path = write_operation_record(tmp_path, "pipeline", {"status": "SUCCESS", "api_key": "must-not-appear"})

    assert path.parent == tmp_path / "logs"
    assert 'must-not-appear' not in path.read_text(encoding="utf-8")
    assert '"status": "SUCCESS"' in path.read_text(encoding="utf-8")
