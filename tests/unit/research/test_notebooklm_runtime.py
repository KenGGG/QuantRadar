"""Static-contract tests for the frozen NotebookLM policy runtime."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace
from contextlib import asynccontextmanager

import pytest

from quantradar.research import notebooklm_runtime as runtime


def test_default_gate_samples_are_indexable_and_traceable(tmp_path: Path) -> None:
    settings = runtime.RuntimeSettings(data_dir=tmp_path, profile_path=tmp_path / "profile", venv_python=Path("/bin/python"))

    assert len("".join(settings.sample_text_body.split())) >= 500
    assert len("".join(settings.sample_pdf_text.split())) >= 500
    assert settings.sample_html_url != "https://example.com"
    assert "[QR-" in runtime._sample_title("PDF", 20260904, settings)
    pdf = runtime._sample_pdf_path(settings)
    contents = pdf.read_bytes()
    assert contents.startswith(b"%PDF-")
    assert b"xref" in contents and b"trailer" in contents and b"%%EOF" in contents


def test_citation_keeps_remote_identity_and_rejects_mismatch() -> None:
    wrong_ref = SimpleNamespace(source_id="remote-other", citation_number=1, cited_text="quoted text", start_char=1, end_char=8, chunk_id="chunk-1", score=0.9)
    with pytest.raises(runtime.RuntimePassError) as caught:
        runtime._extract_citations(7, "expected-source", SimpleNamespace(references=[wrong_ref]), answer="Answer [1]", ledger_source_ids={"expected-source"})
    assert caught.value.code == "CITATION_SOURCE_MISMATCH"


def test_citation_rejects_empty_cited_text_and_missing_answer_marker() -> None:
    ref = SimpleNamespace(source_id="source-1", citation_number=1, cited_text="", start_char=1, end_char=8, chunk_id="chunk-1", score=0.9)
    with pytest.raises(runtime.RuntimePassError) as caught:
        runtime._extract_citations(7, "source-1", SimpleNamespace(references=[ref]), answer="Answer [1]", ledger_source_ids={"source-1"})
    assert caught.value.code == "CITATION_MISSING"


def test_redaction_cleans_secrets_in_keys_and_string_values(tmp_path: Path) -> None:
    payload = {
        "details": "Authorization: Bearer secret-value; Cookie: sid=cookie-value; master token=master-value",
        "url": "https://safe.example/path?token=abc&x=1",
        "credential_path": "/private/path/storage_state.json",
    }
    redacted = runtime._redact_for_log(payload)
    serialized = json.dumps(redacted)
    for secret in ("secret-value", "cookie-value", "master-value", "token=abc", "/private/path/storage_state.json"):
        assert secret not in serialized

    target = tmp_path / "evidence.json"
    runtime._safe_write_json(target, payload, redacted=False)
    assert "secret-value" not in target.read_text(encoding="utf-8")
    assert os.stat(target).st_mode & 0o777 == 0o600


@pytest.mark.parametrize("url", ["https://qyyjt.cn/report", "https://www.qyyjt.cn/report", "https://169.254.1.1/x", "https://100.64.0.1/x"])
def test_public_url_rejects_qyj_and_non_public_addresses(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runtime.socket, "getaddrinfo", lambda *args: [(None, None, None, None, ("8.8.8.8", 0))])
    with pytest.raises(runtime.RuntimePassError) as caught:
        runtime._safe_validate_public_url(url)
    assert caught.value.code == "HTML_URL_REJECTED"


def test_binding_corruption_is_not_treated_as_absent(tmp_path: Path) -> None:
    settings = runtime.RuntimeSettings(data_dir=tmp_path, profile_path=tmp_path / "profile", venv_python=Path("/bin/python"))
    path = runtime._binding_path(settings)
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(runtime.RuntimePassError) as caught:
        runtime._load_binding(settings)
    assert caught.value.code == "BINDING_CORRUPTED"


def test_request_and_result_paths_are_unique_and_private(tmp_path: Path) -> None:
    settings = runtime.RuntimeSettings(data_dir=tmp_path, profile_path=tmp_path / "profile", venv_python=Path("/bin/python"))
    first_request, first_result = runtime._worker_paths(settings, "run-a")
    second_request, second_result = runtime._worker_paths(settings, "run-b")
    assert first_request != second_request and first_result != second_result
    runtime._safe_write_json(first_request, {"ok": True})
    assert os.stat(first_request).st_mode & 0o777 == 0o600


async def _conversation_failure() -> None:
    client = SimpleNamespace(chat=SimpleNamespace(get_conversation_id=_raise_auth))
    await runtime._conversation_id(client, "notebook")


async def _raise_auth(*_args: object) -> None:
    raise runtime.RuntimePassError("AUTH_REQUIRED", "auth failed")


def test_conversation_lookup_does_not_fail_open() -> None:
    with pytest.raises(runtime.RuntimePassError, match="auth failed"):
        asyncio.run(_conversation_failure())


def test_capacity_target_requires_measured_history() -> None:
    settings = runtime.RuntimeSettings(data_dir=Path("/tmp/a"), profile_path=Path("/tmp/p"), venv_python=Path("/bin/python"), historical_max_readable_sources=None)
    with pytest.raises(runtime.RuntimePassError) as caught:
        runtime._capacity_target(settings)
    assert caught.value.code == "SOURCE_CAP_HISTORY_UNAVAILABLE"


@pytest.mark.parametrize("titles, expected", [([], "created"), ([runtime.FIXED_NOTEBOOK_TITLE], "n-0"), ([runtime.FIXED_NOTEBOOK_TITLE, runtime.FIXED_NOTEBOOK_TITLE], "NOTEBOOK_AMBIGUOUS")])
def test_fixed_notebook_exact_match_recovery(tmp_path: Path, titles: list[str], expected: str) -> None:
    class Notebooks:
        async def list(self):
            return [SimpleNamespace(id=f"n-{idx}", title=title) for idx, title in enumerate(titles)]

        async def create(self, title: str):
            return SimpleNamespace(id="created", title=title)

    settings = runtime.RuntimeSettings(data_dir=tmp_path, profile_path=tmp_path / "profile", venv_python=Path("/bin/python"))
    client = SimpleNamespace(notebooks=Notebooks())
    if expected == "NOTEBOOK_AMBIGUOUS":
        with pytest.raises(runtime.RuntimePassError) as caught:
            asyncio.run(runtime._bind_or_create_notebook(client, settings, "web"))
        assert caught.value.code == expected
    else:
        notebook_id, created = asyncio.run(runtime._bind_or_create_notebook(client, settings, "web"))
        assert notebook_id == expected and created is (expected == "created")


def test_existing_binding_title_mismatch_blocks_creation(tmp_path: Path) -> None:
    class Notebooks:
        async def get(self, _notebook_id: str):
            return SimpleNamespace(id="bound", title="renamed remotely")

        async def list(self):
            raise AssertionError("must not fall through to title matching")

    settings = runtime.RuntimeSettings(data_dir=tmp_path, profile_path=tmp_path / "profile", venv_python=Path("/bin/python"))
    runtime._save_binding(settings, "bound", "web")
    with pytest.raises(runtime.RuntimePassError) as caught:
        asyncio.run(runtime._bind_or_create_notebook(SimpleNamespace(notebooks=Notebooks()), settings, "web"))
    assert caught.value.code == "NOTEBOOK_BINDING_MISMATCH"


def test_create_failure_retains_recovery_intent(tmp_path: Path) -> None:
    class Notebooks:
        async def list(self):
            return []

        async def create(self, _title: str):
            raise TimeoutError("provider timeout")

    settings = runtime.RuntimeSettings(data_dir=tmp_path, profile_path=tmp_path / "profile", venv_python=Path("/bin/python"))
    with pytest.raises(runtime.RuntimePassError):
        asyncio.run(runtime._bind_or_create_notebook(SimpleNamespace(notebooks=Notebooks()), settings, "web"))
    assert runtime._load_intent(settings)["state"] == "CREATE_NOTEBOOK"


def test_worker_environment_has_no_unrelated_provider_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUANTRADAR_AGNES_API_KEY", "agnes-secret")
    monkeypatch.setenv("QUANTRADAR_FEISHU_WEBHOOK_URL", "feishu-secret")
    env = runtime._worker_environment(Path("/project"))
    assert "QUANTRADAR_AGNES_API_KEY" not in env and "QUANTRADAR_FEISHU_WEBHOOK_URL" not in env
    assert env["PYTHONPATH"] == "/project/backend"


def test_cleanup_error_does_not_replace_primary_error(tmp_path: Path) -> None:
    result = runtime.RuntimePassResult()
    result.pipeline_error_code = "SOURCE_UPLOAD_FAILED"
    result.cleanup_error_code = "SOURCE_DELETE_FAILED"
    result.error_code = result.pipeline_error_code
    runtime._safe_write_json(tmp_path / "result.json", result.as_json())
    payload = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert payload["pipeline_error_code"] == "SOURCE_UPLOAD_FAILED"
    assert payload["cleanup_error_code"] == "SOURCE_DELETE_FAILED"
    assert payload["error_code"] == "SOURCE_UPLOAD_FAILED"


def test_from_env_uses_frozen_safety_margin_and_measured_history(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runtime, "_historical_max_daily_readable_unique_reports", lambda: 87)
    monkeypatch.setenv("QUANTRADAR_NOTEBOOKLM_SOURCE_SAFETY_MARGIN", "13")
    settings = runtime.RuntimeSettings.from_env(tmp_path)
    assert settings.historical_max_readable_sources == 87
    assert runtime._capacity_target(settings) == 100


def test_worker_timeout_is_explicit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = runtime.RuntimeSettings(data_dir=tmp_path, profile_path=tmp_path / "profile", venv_python=Path("/bin/python"), worker_timeout_seconds=1)
    monkeypatch.setattr(runtime, "ensure_runtime_locked", lambda _settings: None)

    def timeout(*_args: object, **_kwargs: object):
        raise runtime.subprocess.TimeoutExpired("worker", 1)

    monkeypatch.setattr(runtime.subprocess, "run", timeout)
    with pytest.raises(runtime.RuntimePassError) as caught:
        runtime.run_policy_runtime_pass_via_worker(settings)
    assert caught.value.code == "WORKER_TIMEOUT"
    assert json.loads(runtime._evidence_path(settings).read_text(encoding="utf-8"))["pipeline_error_code"] == "WORKER_TIMEOUT"


def test_lifecycle_resets_before_capacity_and_requires_all_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    settings = runtime.RuntimeSettings(data_dir=tmp_path, profile_path=tmp_path / "profile", venv_python=Path("/bin/python"), use_worker=False, historical_max_readable_sources=1)

    async def probe(_settings: object, backend: str):
        return runtime.BackendProbeResult(backend=backend, auth_ok=True, upload_ok=True, fulltext_ok=True, ask_ok=True, reset_ok=True)

    @asynccontextmanager
    async def client_context(*_args: object):
        yield SimpleNamespace()

    async def bind(*_args: object):
        return "fixed", False

    async def reset(*_args: object):
        events.append("reset")

    async def capacity(*_args: object):
        events.append("capacity")
        return {"historical_max": 1, "margin": 10, "target": 11}

    async def sources(*_args: object):
        return []

    async def conversation(*_args: object):
        return None

    async def source_attempt(_client: object, _notebook: str, _settings: object, kind: str, payload: dict[str, str], **kwargs: object):
        report_id = int(kwargs["report_id"])
        attempt = runtime.SourceAttempt(1, report_id, kind, f"source-{report_id}", payload["title"], True, True, "snapshot", "hash", 500, None, True, "conversation")
        return attempt, [], True

    monkeypatch.setattr(runtime, "_run_backend_probe", probe)
    monkeypatch.setattr(runtime, "_acquire_client", client_context)
    monkeypatch.setattr(runtime, "_bind_or_create_notebook", bind)
    monkeypatch.setattr(runtime, "_reset_workspace_health", reset)
    monkeypatch.setattr(runtime, "_capacity_gate", capacity)
    monkeypatch.setattr(runtime, "_list_notebook_sources", sources)
    monkeypatch.setattr(runtime, "_conversation_id", conversation)
    monkeypatch.setattr(runtime, "_run_single_source_attempt", source_attempt)
    monkeypatch.setattr(runtime, "_preflight_public_url", lambda url: url)

    result = asyncio.run(runtime._run_policy_runtime_pass_locked(settings))
    assert result.status == "READY" and result.cleanup_status == "PASS"
    assert events.index("reset") < events.index("capacity")
    assert len(result.source_records) == 3 and result.source_count_after_cleanup == 0


def test_capacity_gate_cannot_be_disabled(tmp_path: Path) -> None:
    settings = runtime.RuntimeSettings(data_dir=tmp_path, profile_path=tmp_path / "profile", venv_python=Path("/bin/python"), historical_max_readable_sources=0, source_capacity_probe_enabled=False)
    with pytest.raises(runtime.RuntimePassError) as caught:
        asyncio.run(runtime._capacity_gate(SimpleNamespace(), "fixed", settings))
    assert caught.value.code == "SOURCE_CAP_GATE_REQUIRED"


def test_atomic_fulltext_snapshot_never_writes_final_path_directly(tmp_path: Path) -> None:
    target = tmp_path / "fulltext.txt"
    runtime._atomic_write_text(target, "indexed content")
    assert target.read_text(encoding="utf-8") == "indexed content"
    assert not target.with_suffix(".part").exists()
    assert os.stat(target).st_mode & 0o777 == 0o600


def test_runtime_preflight_failure_writes_structured_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = runtime.RuntimeSettings(data_dir=tmp_path, profile_path=tmp_path / "profile", venv_python=Path("/missing"), use_worker=False)
    monkeypatch.setattr(runtime, "ensure_runtime_locked", lambda _settings: (_ for _ in ()).throw(runtime.RuntimePassError("PROVIDER_API_DRIFT", "bad runtime")))
    with pytest.raises(runtime.RuntimePassError):
        asyncio.run(runtime.run_policy_runtime_pass(settings))
    payload = json.loads(runtime._evidence_path(settings).read_text(encoding="utf-8"))
    assert payload["pipeline_error_code"] == "PROVIDER_API_DRIFT"


def test_worker_mode_refuses_direct_execution_without_parent_lock_token(tmp_path: Path) -> None:
    request = tmp_path / "request.json"
    runtime._write_private_worker_json(request, {"data_dir": str(tmp_path), "profile_path": str(tmp_path / "profile"), "venv_python": "/bin/python"})
    with pytest.raises(runtime.RuntimePassError) as caught:
        runtime._run_worker_mode(request, tmp_path / "result.json")
    assert caught.value.code == "WORKER_LOCK_OWNERSHIP_INVALID"


def test_backend_probe_rejects_answer_without_citations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class NotFound(Exception):
        pass

    class Notebooks:
        async def list(self):
            return []

        async def create(self, _title: str):
            return SimpleNamespace(id="probe")

        async def delete(self, _notebook_id: str):
            return None

        async def get(self, _notebook_id: str):
            raise NotFound("not found notebook")

    class Sources:
        async def add_file(self, *_args: object, **_kwargs: object):
            return SimpleNamespace(id="s1", status="ready")

        async def add_text(self, *_args: object, **_kwargs: object):
            return SimpleNamespace(id="s2", status="ready")

        async def add_url(self, *_args: object, **_kwargs: object):
            return SimpleNamespace(id="s3", status="ready")

        async def get_fulltext(self, *_args: object, **_kwargs: object):
            return SimpleNamespace(content="x" * 500, title="sample")

        async def delete(self, *_args: object):
            return None

        async def list(self, *_args: object):
            return []

    class Chat:
        async def get_conversation_id(self, *_args: object):
            return None

        async def ask(self, *_args: object, **_kwargs: object):
            return SimpleNamespace(conversation_id="c1", answer="answer", references=[])

        async def delete_conversation(self, *_args: object):
            return None

    @asynccontextmanager
    async def client_context(*_args: object):
        yield SimpleNamespace(notebooks=Notebooks(), sources=Sources(), chat=Chat())

    settings = runtime.RuntimeSettings(data_dir=tmp_path, profile_path=tmp_path / "profile", venv_python=Path("/bin/python"))
    monkeypatch.setattr(runtime, "_acquire_client", client_context)
    monkeypatch.setattr(runtime, "_preflight_public_url", lambda url: url)
    result = asyncio.run(runtime._run_backend_probe(settings, "web"))
    assert result.error_code == "CITATION_MISSING" and not result.ask_ok
