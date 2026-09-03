"""Runtime implementation for ``NOTEBOOKLM_POLICY_RUNTIME_PASS``.

This module runs a strict, bounded NotebookLM runtime smoke path for the frozen
policy architecture:

- one fixed Notebook;
- one exclusive workspace lock covering reset/upload/analysis/cleanup;
- JSON runtime via a dedicated ``.venv-notebooklm`` process in normal execution.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import socket
import time
import subprocess
import sys
import ipaddress
import importlib.util
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable
from urllib.parse import parse_qs, urlparse

try:
    from .operations import ResearchRunLock, write_operation_record
except Exception:
    _operations_path = Path(__file__).resolve().parent / "operations.py"
    _operations_spec = importlib.util.spec_from_file_location("_notebooklm_runtime_operations", _operations_path)
    if _operations_spec is None or _operations_spec.loader is None:
        raise
    _operations_module = importlib.util.module_from_spec(_operations_spec)
    _operations_spec.loader.exec_module(_operations_module)
    ResearchRunLock = _operations_module.ResearchRunLock
    write_operation_record = _operations_module.write_operation_record

NOTEBOOKLM_RUNTIME_GOAL = "NOTEBOOKLM_POLICY_RUNTIME_PASS"
NOTEBOOKLM_EXPECTED_VERSION = "0.8.2"
FIXED_NOTEBOOK_TITLE = "QuantRadar Research Daily Digest"
FIXED_BINDING_KEY = "research_daily_digest"
WORKSPACE_SOURCE_RESET_SECONDS = 120.0
WORKSPACE_CONVERSATION_RESET_SECONDS = 60.0


def now_iso8601() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class RuntimePassError(RuntimeError):
    """Runtime failure with a stable machine-readable code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class _RuntimeWorkerError(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeSettings:
    data_dir: Path
    profile_path: Path
    venv_python: Path
    binding_key: str = FIXED_BINDING_KEY
    notebook_title: str = FIXED_NOTEBOOK_TITLE
    backend_candidates: tuple[str, ...] = ("web", "android")
    backend_selection_preference: str = "web"
    source_capacity_margin: int = 10
    historical_max_readable_sources: int = 0
    lock_name: str = "notebooklm-runtime-policy.lock"
    evidence_name: str = "notebooklm-runtime-pass-result.json"
    sample_pdf_path: Path | None = None
    sample_pdf_text: str = (
        "QuantRadar 研究 NotebookLM 验收样本。\n"
        "这是非敏感测试文本，长度足够长以满足全文索引验证。"
        "用于验证 NotebookLM Source 上传、READY 检测、全文快照及引用映射。"
    )
    sample_text_title: str = "QuantRadar NotebookLM Policy Runtime PASS"
    sample_text_body: str = (
        "非敏感测试正文。本文仅用于 NotebookLM 运行时验收，不含真实投资建议。"
        "用于验证 add_text、wait_until_ready、get_fulltext 与 ask 的完整流程。"
    )
    sample_html_url: str = "https://example.com"
    capacity_gate_timeout_seconds: float = 900.0
    source_ready_timeout_seconds: float = 900.0
    ask_timeout_seconds: float = 120.0
    use_worker: bool = True
    source_capacity_probe_enabled: bool = True

    @classmethod
    def from_env(cls, data_dir: Path | None = None) -> "RuntimeSettings":
        project_root = Path(__file__).resolve().parents[3]
        runtime_data_dir = Path(
            os.environ.get(
                "QUANTRADAR_RESEARCH_DATA_DIR",
                str(project_root / ".cache/quantradar/research"),
            )
        )
        candidate_env = os.environ
        venv = Path(
            candidate_env.get(
                "QUANTRADAR_NOTEBOOKLM_VENV",
                str(project_root / ".venv-notebooklm/bin/python"),
            )
        )
        if data_dir is None:
            data_dir = runtime_data_dir
        return cls(
            data_dir=Path(data_dir),
            profile_path=Path(
                candidate_env.get(
                    "QUANTRADAR_NOTEBOOKLM_PROFILE",
                    str(project_root / ".cache/quantradar/notebooklm/storage_state.json"),
                )
            ),
            venv_python=venv,
            backend_selection_preference=candidate_env.get("QUANTRADAR_NOTEBOOKLM_BACKEND_PREFERENCE", "web"),
            backend_candidates=tuple(
                item.strip() for item in candidate_env.get("QUANTRADAR_NOTEBOOKLM_BACKENDS", "web,android").split(",") if item.strip()
            ) or ("web", "android"),
            source_capacity_margin=int(candidate_env.get("QUANTRADAR_NOTEBOOKLM_SOURCE_CAPACITY_MARGIN", "10")),
            historical_max_readable_sources=int(candidate_env.get("QUANTRADAR_NOTEBOOKLM_HISTORICAL_MAX_READABLE", "0")),
            sample_pdf_path=Path(candidate_env["QUANTRADAR_NOTEBOOKLM_SAMPLE_PDF"]) if candidate_env.get("QUANTRADAR_NOTEBOOKLM_SAMPLE_PDF") else None,
            sample_pdf_text=candidate_env.get("QUANTRADAR_NOTEBOOKLM_SAMPLE_PDF_TEXT", cls.sample_pdf_text),
            sample_text_title=candidate_env.get("QUANTRADAR_NOTEBOOKLM_SAMPLE_TEXT_TITLE", cls.sample_text_title),
            sample_text_body=candidate_env.get("QUANTRADAR_NOTEBOOKLM_SAMPLE_TEXT_BODY", cls.sample_text_body),
            sample_html_url=candidate_env.get("QUANTRADAR_NOTEBOOKLM_SAMPLE_HTML_URL", cls.sample_html_url),
            use_worker=candidate_env.get("QUANTRADAR_NOTEBOOKLM_USE_WORKER", "1") not in {"0", "false", "False", "no", "No"},
            capacity_gate_timeout_seconds=float(candidate_env.get("QUANTRADAR_NOTEBOOKLM_CAPACITY_GATE_TIMEOUT", "900")),
            source_ready_timeout_seconds=float(candidate_env.get("QUANTRADAR_NOTEBOOKLM_SOURCE_READY_TIMEOUT", "900")),
            ask_timeout_seconds=float(candidate_env.get("QUANTRADAR_NOTEBOOKLM_ASK_TIMEOUT", "120")),
            source_capacity_probe_enabled=candidate_env.get("QUANTRADAR_NOTEBOOKLM_RUN_CAPACITY_GATE", "1") not in {"0", "false", "False", "no", "No"},
        )

    def to_request_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["data_dir"] = str(self.data_dir)
        payload["profile_path"] = str(self.profile_path)
        payload["venv_python"] = str(self.venv_python)
        if self.sample_pdf_path is not None:
            payload["sample_pdf_path"] = str(self.sample_pdf_path)
        else:
            payload["sample_pdf_path"] = None
        return payload


@dataclass
class BackendProbeResult:
    backend: str
    auth_ok: bool = False
    upload_ok: bool = False
    fulltext_ok: bool = False
    ask_ok: bool = False
    reset_ok: bool = False
    error_code: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SourceAttempt:
    attempt_index: int
    report_id: int
    source_kind: str
    remote_source_id: str
    title: str
    selected_for_analysis: bool
    ready: bool
    fulltext_path: str
    fulltext_sha256: str
    fulltext_char_count: int
    fallback_reason: str | None
    deleted_after_use: bool
    error: str | None = None
    deletion_error: str | None = None


@dataclass
class CitationRecord:
    report_id: int
    source_id: str
    citation_number: int | None
    cited_text: str | None
    start_char: int | None
    end_char: int | None
    chunk_id: str | None
    score: float | None


@dataclass
class RuntimePassResult:
    goal: str = NOTEBOOKLM_RUNTIME_GOAL
    timestamp: str = field(default_factory=now_iso8601)
    selected_backend: str | None = None
    backend_comparison: list[dict[str, Any]] = field(default_factory=list)
    fixed_notebook_id: str | None = None
    fixed_notebook_created: bool = False
    fixed_notebook_binding_key: str = FIXED_BINDING_KEY
    source_records: list[dict[str, Any]] = field(default_factory=list)
    citation_records: list[dict[str, Any]] = field(default_factory=list)
    source_count_before_cleanup: int = 0
    source_count_after_cleanup: int = 0
    conversation_state_before_cleanup: str | None = None
    conversation_state_after_cleanup: str | None = None
    status: str = "READY_CANDIDATE"
    error_code: str | None = None

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


RETRY_ATTEMPTS = (1, 2, 4)
SENSITIVE_URL_QUERY_KEYS = {
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "signature",
    "sig",
    "s",
    "signature_key",
    "auth",
    "authorization",
    "password",
    "pwd",
    "session",
    "cookie",
}


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return text


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _safe_write_json(target: Path, payload: dict[str, Any], *, redacted: bool = True) -> None:
    if redacted:
        payload = _redact_for_log(payload)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = target.with_suffix(".part")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(target)


def _redact_for_log(payload: Any) -> Any:
    if isinstance(payload, dict):
        out: dict[str, Any] = {}
        for key, value in payload.items():
            if any(token in key.lower() for token in ("token", "cookie", "secret", "auth", "session")):
                out[key] = "[REDACTED]"
            else:
                out[key] = _redact_for_log(value)
        return out
    if isinstance(payload, list):
        return [_redact_for_log(item) for item in payload]
    return payload


def _build_retryable_delete(func: Callable[[], Awaitable[None]], exists_fn: Callable[[], Awaitable[bool]], *,
                          attempts: tuple[int, ...] = RETRY_ATTEMPTS, sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
                          ) -> Awaitable[None]:
    async def _runner() -> None:
        for delay in attempts:
            try:
                await func()
            except Exception:
                pass
            if not await exists_fn():
                return
            await sleeper(float(delay))
        if await exists_fn():
            raise RuntimePassError("NOTEBOOK_DIRTY", "Cleanup failed after bounded retries")

    return _runner()


def _resolve_notebooklm_version(python: Path) -> str:
    if not python.is_file():
        raise RuntimePassError("PROVIDER_API_DRIFT", f"notebooklm runtime python missing: {python}")
    command = [
        str(python),
        "-c",
        (
            "from importlib.metadata import version, PackageNotFoundError;"
            "import sys;"
            "\ntry:\n  print(version('notebooklm-py'))\nexcept PackageNotFoundError:\n  print(__import__('notebooklm').__version__)\n"
        ),
    ]
    completed = subprocess.run(command, text=True, capture_output=True)
    if completed.returncode != 0:
        raise RuntimePassError("PROVIDER_API_DRIFT", "notebooklm runtime import/version check failed")
    observed = (completed.stdout or "").strip().splitlines()[-1].strip()
    if not observed:
        raise RuntimePassError("PROVIDER_API_DRIFT", "notebooklm runtime version result is empty")
    return observed


def ensure_runtime_locked(settings: RuntimeSettings) -> None:
    observed = _resolve_notebooklm_version(settings.venv_python)
    if observed != NOTEBOOKLM_EXPECTED_VERSION:
        raise RuntimePassError("PROVIDER_API_DRIFT", f"notebooklm-py mismatch: expected {NOTEBOOKLM_EXPECTED_VERSION}, got {observed}")


def _is_private_host(host: str) -> bool:
    h = host.lower()
    if h in {"localhost", "::1", "127.0.0.1", "0.0.0.0", "::"}:
        return True
    if h.endswith(".localhost") or h.startswith("127."):
        return True
    if h in {"local", "qyj.cn", "qyj.com", "www.qyj.com", "qianyanjingji.com"}:
        return True
    if h.startswith("10.") or h.startswith("192.168.") or h.startswith("172."):
        return True
    if h.endswith(".internal") or h.startswith("::ffff:"):
        return True
    return False


@asynccontextmanager
async def _acquire_workspace_lock(lock_path: Path):
    with ResearchRunLock(lock_path) as lock:
        yield lock


async def _bounded_await(predicate: Callable[[], Awaitable[bool]], deadline_seconds: float, message: str, *, interval: float = 0.5) -> None:
    deadline = time.monotonic() + float(deadline_seconds)
    while time.monotonic() < deadline:
        if await predicate():
            return
        await asyncio.sleep(interval)
        interval = min(interval * 1.4, 2.0)
    raise RuntimePassError("NOTEBOOK_DIRTY", message)


def _safe_validate_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise RuntimePassError("HTML_URL_REJECTED", "Only http/https URLs are allowed")
    if parsed.username or parsed.password:
        raise RuntimePassError("HTML_URL_REJECTED", "Credentials in URL are not allowed")
    if not parsed.hostname:
        raise RuntimePassError("HTML_URL_REJECTED", "Invalid URL")
    host = parsed.hostname.lower()
    if _is_private_host(host):
        raise RuntimePassError("HTML_URL_REJECTED", "Private/localhost URL denied")
    query = parse_qs(parsed.query or "")
    if any(k.lower() in SENSITIVE_URL_QUERY_KEYS for k in query.keys()):
        raise RuntimePassError("HTML_URL_REJECTED", "Sensitive query parameters detected")
    try:
        infos = socket.getaddrinfo(
            host,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            0,
            0,
            0,
            0,
        )
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private:
                raise RuntimePassError("HTML_URL_REJECTED", "URL resolves to private IP")
            if ip.is_loopback:
                raise RuntimePassError("HTML_URL_REJECTED", "URL resolves to loopback IP")
            if ip.is_reserved:
                raise RuntimePassError("HTML_URL_REJECTED", "URL resolves to reserved IP")
            if ip.is_multicast:
                raise RuntimePassError("HTML_URL_REJECTED", "URL resolves to multicast IP")
    except RuntimePassError:
        raise
    except OSError:
        raise RuntimePassError("HTML_URL_REJECTED", "URL DNS resolution failed")
    except Exception as exc:
        raise RuntimePassError("HTML_URL_REJECTED", f"URL host validation failed: {exc}")
    return url


def _error_code_from_exception(exc: Exception) -> str:
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    if "storage file not found" in message and "notebooklm login" in message:
        return "AUTH_REQUIRED"
    if "auth" in name or "token" in message or "cookie" in message:
        return "AUTH_REQUIRED"
    if "not found" in message and "notebook" in message:
        return "NOTEBOOK_MISSING"
    if "rate" in message and "limit" in message:
        return "CHAT_RATE_LIMITED"
    if "timeout" in message:
        return "SOURCE_READY_TIMEOUT"
    if "processing" in name or "source" in name and "error" in name:
        return "SOURCE_PROCESSING_FAILED"
    return "PROVIDER_API_DRIFT"


def _to_int_status(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped in {"ready", "processing", "error", "preparing", "unknown"}:
            mapping = {
                "unknown": -1,
                "processing": 1,
                "ready": 2,
                "error": 3,
                "preparing": 5,
            }
            return mapping.get(stripped)
        try:
            return int(stripped)
        except ValueError:
            return None
    return None


def _source_is_ready(source: Any) -> bool:
    status = _to_int_status(getattr(source, "status", None))
    if status is None:
        status_attr = getattr(source, "status", None)
        if status_attr is None:
            return False
        return str(status_attr).lower() in {"ready"}
    return status == 2


def _find_ready_source(records: Iterable[Any], source_id: str) -> Any | None:
    for item in records:
        if getattr(item, "id", None) == source_id:
            return item
    return None


def _status_label(value: Any) -> str:
    status = _to_int_status(value)
    mapping = {
        2: "READY",
        1: "PROCESSING",
        3: "ERROR",
        5: "PREPARING",
    }
    if status in mapping:
        return mapping[status]
    return str(value)


def _extract_citations(report_id: int, source_id: str, ask_result: Any) -> list[CitationRecord]:
    refs = []
    for ref in getattr(ask_result, "references", []) or []:
        refs.append(
            CitationRecord(
                report_id=report_id,
                source_id=str(source_id),
                citation_number=getattr(ref, "citation_number", None),
                cited_text=getattr(ref, "cited_text", None),
                start_char=getattr(ref, "start_char", None),
                end_char=getattr(ref, "end_char", None),
                chunk_id=getattr(ref, "chunk_id", None),
                score=getattr(ref, "score", None),
            )
        )
    return refs


def _sample_pdf_path(settings: RuntimeSettings) -> Path:
    if settings.sample_pdf_path is not None:
        return settings.sample_pdf_path
    path = settings.data_dir / "notebooklm" / "runtime-sample.pdf"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    header = "%%PDF-1.4\n%\xE2\xE3\xCF\xD3\n"
    body = settings.sample_pdf_text or ""
    path.write_bytes((header + body + "\n%%EOF\n").encode("utf-8"))
    return path


def _binding_path(settings: RuntimeSettings) -> Path:
    return settings.data_dir / "notebooklm" / "binding.json"


def _binding_intent_path(settings: RuntimeSettings) -> Path:
    return settings.data_dir / "notebooklm" / "binding-intent.json"


def _evidence_path(settings: RuntimeSettings) -> Path:
    return settings.data_dir / "notebooklm" / settings.evidence_name


def _fulltext_directory(settings: RuntimeSettings) -> Path:
    return settings.data_dir / "notebooklm" / "fulltext"


def _load_json_obj(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _save_binding(settings: RuntimeSettings, notebook_id: str, backend: str) -> None:
    _binding_path(settings).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = {
        "binding_key": settings.binding_key,
        "notebook_id": notebook_id,
        "provider": "notebooklm",
        "notebook_title": settings.notebook_title,
        "backend": backend,
        "provider_version": NOTEBOOKLM_EXPECTED_VERSION,
        "state": "BOUND",
        "updated_at": now_iso8601(),
    }
    _safe_write_json(_binding_path(settings), payload)


def _save_intent(settings: RuntimeSettings, action: str, notebook_id: str | None, backend: str) -> dict[str, Any]:
    intent = {
        "binding_key": settings.binding_key,
        "notebook_title": settings.notebook_title,
        "expected_backend": backend,
        "attempt": action,
        "notebook_id": notebook_id,
        "state": action,
        "updated_at": now_iso8601(),
    }
    _safe_write_json(_binding_intent_path(settings), intent)
    return intent


def _clear_intent(settings: RuntimeSettings) -> None:
    path = _binding_intent_path(settings)
    if path.exists():
        path.unlink()


@asynccontextmanager
async def _acquire_client(backend: str, settings: RuntimeSettings):
    from notebooklm import NotebookLMClient

    async with NotebookLMClient.from_storage(path=str(settings.profile_path), backend=backend) as client:
        yield client


async def _list_notebook_sources(client: Any, notebook_id: str):
    return await client.sources.list(notebook_id)


async def _conversation_id(client: Any, notebook_id: str) -> str | None:
    try:
        value = await client.chat.get_conversation_id(notebook_id)
        return value
    except Exception:
        return None


async def _delete_conversation_with_retries(client: Any, notebook_id: str) -> None:
    async def _exists() -> bool:
        cid = await _conversation_id(client, notebook_id)
        return bool(cid)

    async def _delete() -> None:
        cid = await _conversation_id(client, notebook_id)
        if cid:
            await client.chat.delete_conversation(notebook_id, cid)

    await _build_retryable_delete(_delete, _exists)


async def _delete_source_with_retries(client: Any, notebook_id: str, source_id: str) -> None:
    async def _exists() -> bool:
        sources = await _list_notebook_sources(client, notebook_id)
        return any(source.id == source_id for source in sources)

    async def _delete() -> None:
        await client.sources.delete(notebook_id, source_id)

    await _build_retryable_delete(_delete, _exists)


async def _reset_workspace_health(client: Any, notebook_id: str) -> None:
    async def _reset_sources() -> None:
        sources = await _list_notebook_sources(client, notebook_id)
        for source in list(sources):
            await _delete_source_with_retries(client, notebook_id, source.id)

    async def _source_list_empty() -> bool:
        return len(await _list_notebook_sources(client, notebook_id)) == 0

    await _reset_sources()
    try:
        await _bounded_await(_source_list_empty, WORKSPACE_SOURCE_RESET_SECONDS, "Source reset timeout: residual sources remain")
    except RuntimePassError as exc:
        raise RuntimePassError("NOTEBOOK_DIRTY", str(exc))

    async def _conversation_absent() -> bool:
        return not bool(await _conversation_id(client, notebook_id))

    current_cid = await _conversation_id(client, notebook_id)
    if not current_cid:
        return

    while current_cid:
        await _delete_conversation_with_retries(client, notebook_id)
        try:
            await _bounded_await(
                _conversation_absent,
                WORKSPACE_CONVERSATION_RESET_SECONDS,
                "Conversation reset timeout",
                interval=0.5,
            )
        except RuntimePassError as exc:
            raise RuntimePassError("CONVERSATION_RESET_FAILED", str(exc))
        current_cid = await _conversation_id(client, notebook_id)


async def _wait_source_ready(client: Any, notebook_id: str, source_id: str, *, timeout: float) -> Any:
    return await client.sources.wait_until_ready(
        notebook_id,
        source_id,
        timeout=timeout,
        initial_interval=1.0,
        max_interval=10.0,
        backoff_factor=1.5,
    )


async def _fetch_fulltext(client: Any, notebook_id: str, source_id: str) -> tuple[str, int, str]:
    text_obj = await client.sources.get_fulltext(notebook_id, source_id, output_format="text")
    content = _strip_frontmatter(_normalize_text(getattr(text_obj, "rendered_content", getattr(text_obj, "content", "")))
    )
    if not content or len(content) < 200:
        raise RuntimePassError("INDEXED_CONTENT_INVALID", "Indexed text below threshold")
    title = str(getattr(text_obj, "title", ""))
    if title and len(content) <= len(_normalize_text(title)):
        raise RuntimePassError("INDEXED_CONTENT_INVALID", "Indexed content too short or title-only")
    digest = _sha256_hex(content)
    char_count = len(content)
    return content, char_count, digest


async def _ask_with_explicit_source(
    client: Any,
    notebook_id: str,
    source_id: str,
    question: str,
    *,
    timeout_seconds: float = 120.0,
) -> tuple[Any, str | None]:
    await _delete_conversation_with_retries(client, notebook_id)
    ask_result = await asyncio.wait_for(
        client.chat.ask(notebook_id, question, source_ids=[source_id]),
        timeout=timeout_seconds,
    )
    conv_id = getattr(ask_result, "conversation_id", None)
    if not conv_id:
        raise RuntimePassError("CHAT_EMPTY", "Chat ask did not return conversation_id")
    try:
        await _delete_conversation_with_retries(client, notebook_id)
    except RuntimePassError:
        pass
    return ask_result, conv_id


async def _run_backend_probe(settings: RuntimeSettings, backend: str) -> BackendProbeResult:
    result = BackendProbeResult(backend=backend)
    try:
        async with _acquire_client(backend, settings) as client:
            await client.notebooks.list()
            result.auth_ok = True
            probe_title = f"{settings.notebook_title}-probe-{backend}"
            notebook = await client.notebooks.create(probe_title)
            notebook_id = notebook.id
            source = None
            try:
                source = await client.sources.add_text(
                    notebook_id,
                    f"policy-{backend}",
                    "Policy runtime probe text",
                    wait=True,
                )
                if not _source_is_ready(source):
                    source = await _wait_source_ready(
                        client,
                        notebook_id,
                        source.id,
                        timeout=settings.source_ready_timeout_seconds,
                    )
                result.upload_ok = True
                _, _, digest = await _fetch_fulltext(client, notebook_id, source.id)
                result.fulltext_ok = True
                result.details["fulltext_digest"] = digest
                await _delete_conversation_with_retries(client, notebook_id)
                ask_result, _ = await _ask_with_explicit_source(
                    client,
                    notebook_id,
                    source.id,
                    "这条样本是什么？",
                    timeout_seconds=settings.ask_timeout_seconds,
                )
                result.ask_ok = bool(getattr(ask_result, "references", []))
                result.details["ask_reference_count"] = len(getattr(ask_result, "references", []))
                await _delete_conversation_with_retries(client, notebook_id)
            finally:
                if source is not None and getattr(source, "id", None):
                    try:
                        await _delete_source_with_retries(client, notebook_id, source.id)
                    except Exception:
                        pass
                await client.notebooks.delete(notebook_id)
            result.reset_ok = True
            return result
    except RuntimePassError as exc:
        result.error_code = exc.code
        result.details["error"] = exc.detail
        return result
    except Exception as exc:
        result.error_code = _error_code_from_exception(exc)
        result.details["error"] = str(exc)
        return result


async def _capacity_gate(client: Any, notebook_id: str, settings: RuntimeSettings) -> None:
    if not settings.source_capacity_probe_enabled:
        return
    target = settings.historical_max_readable_sources + settings.source_capacity_margin
    if target <= 0:
        return
    created: list[str] = []
    source_ids: list[str] = []
    try:
        for index in range(target):
            source = await client.sources.add_text(
                notebook_id,
                f"capacity-{index}",
                "cap" * 80,
            )
            created.append(source.id)
            source_ids.append(source.id)
        for source_id in source_ids:
            await _wait_source_ready(client, notebook_id, source_id, timeout=settings.capacity_gate_timeout_seconds)
        for source_id in created:
            await _delete_source_with_retries(client, notebook_id, source_id)
    except Exception as exc:
        for source_id in source_ids:
            try:
                await _delete_source_with_retries(client, notebook_id, source_id)
            except Exception:
                pass
        raise RuntimePassError("SOURCE_CAP_EXCEEDED", f"Capacity gate failed: {exc}") from exc


async def _bind_or_create_notebook(
    client: Any,
    settings: RuntimeSettings,
    backend: str,
) -> tuple[str, bool]:
    binding = _load_json_obj(_binding_path(settings)) or {}
    binding_id = binding.get("notebook_id") if isinstance(binding, dict) else None

    if binding_id:
        try:
            notebook = await client.notebooks.get(binding_id)
            if getattr(notebook, "id", None) == binding_id and str(getattr(notebook, "title", "")) == settings.notebook_title:
                return binding_id, False
        except Exception as exc:
            if any(word in type(exc).__name__.lower() for word in {"notebooknotfound", "notfound", "notfounderror"}):
                raise RuntimePassError("NOTEBOOK_MISSING", f"Saved notebook missing: {binding_id}") from exc
            # Keep binding and fail on auth/network/compatibility drift.
            raise

    exact_matches = [
        nb
        for nb in await client.notebooks.list()
        if str(getattr(nb, "title", "")) == settings.notebook_title
    ]
    if exact_matches:
        if len(exact_matches) > 1:
            raise RuntimePassError("NOTEBOOK_AMBIGUOUS", "Multiple fixed-title notebooks found")
        notebook_id = exact_matches[0].id
        _save_binding(settings, notebook_id, backend)
        return notebook_id, False

    _save_intent(settings, "CREATE_NOTEBOOK", None, backend)
    try:
        created = await client.notebooks.create(settings.notebook_title)
        notebook_id = created.id
    except Exception as exc:
        _clear_intent(settings)
        raise RuntimePassError("PROVIDER_API_DRIFT", f"Fixed notebook create failed: {exc}") from exc
    _save_binding(settings, notebook_id, backend)
    _clear_intent(settings)
    return notebook_id, True


async def _run_single_source_attempt(
    client: Any,
    notebook_id: str,
    settings: RuntimeSettings,
    source_kind: str,
    payload: dict[str, str],
    *,
    attempt_index: int,
    report_id: int,
    fulltext_dir: Path,
    timeout: float,
) -> tuple[SourceAttempt, list[CitationRecord], bool]:
    fulltext_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    source_id = ""
    deletion_error: str | None = None
    try:
        if source_kind == "PDF":
            source = await client.sources.add_file(
                notebook_id,
                payload["file_path"],
                title=payload["title"],
                wait=False,
            )
        elif source_kind == "WEIXIN_TEXT":
            source = await client.sources.add_text(
                notebook_id,
                payload["title"],
                payload["text"],
                wait=False,
            )
        elif source_kind == "HTML_URL":
            source = await client.sources.add_url(
                notebook_id,
                payload["url"],
                title=payload["title"],
                wait=False,
            )
        else:
            raise RuntimePassError("SOURCE_UPLOAD_FAILED", f"Unsupported source kind: {source_kind}")

        source_id = getattr(source, "id", "")
        ready_source = source
        if not _source_is_ready(source):
            ready_source = await _wait_source_ready(client, notebook_id, source_id, timeout=timeout)
        if not _source_is_ready(ready_source):
            raise RuntimePassError("SOURCE_READY_TIMEOUT", "Source not READY")

        content, char_count, digest = await _fetch_fulltext(client, notebook_id, source_id)
        snapshot = fulltext_dir / f"{source_id}.txt"
        snapshot.write_text(content, encoding="utf-8")

        await _delete_conversation_with_retries(client, notebook_id)
        ask_result, _ = await _ask_with_explicit_source(
            client,
            notebook_id,
            source_id,
            "请给出这份材料的核心要点",
            timeout_seconds=settings.ask_timeout_seconds,
        )
        citations = _extract_citations(report_id, source_id, ask_result)

        if not citations:
            raise RuntimePassError("CITATION_MISSING", "No citations returned")
        citation_payload = [asdict(item) for item in citations]
        attempt = SourceAttempt(
            attempt_index=attempt_index,
            report_id=report_id,
            source_kind=source_kind,
            remote_source_id=source_id,
            title=payload["title"],
            selected_for_analysis=True,
            ready=True,
            fulltext_path=str(snapshot),
            fulltext_sha256=digest,
            fulltext_char_count=char_count,
            fallback_reason=None,
            deleted_after_use=False,
            error=None,
            deletion_error=None,
        )
        try:
            await _delete_source_with_retries(client, notebook_id, source_id)
            attempt.deleted_after_use = True
        except Exception as exc:
            deletion_error = str(exc)
            attempt.deleted_after_use = False
            attempt.deletion_error = deletion_error
        return attempt, citation_payload, True

    except RuntimePassError as exc:
        if source_id:
            try:
                await _delete_source_with_retries(client, notebook_id, source_id)
                deletion_error = None
            except Exception as delete_exc:
                deletion_error = str(delete_exc)
        attempt = SourceAttempt(
            attempt_index=attempt_index,
            report_id=report_id,
            source_kind=source_kind,
            remote_source_id=source_id,
            title=payload.get("title", ""),
            selected_for_analysis=False,
            ready=False,
            fulltext_path="",
            fulltext_sha256="",
            fulltext_char_count=0,
            fallback_reason=exc.code,
            deleted_after_use=False,
            error=exc.detail,
            deletion_error=deletion_error,
        )
        return attempt, [], False
    except Exception as exc:
        code = _error_code_from_exception(exc)
        if source_id:
            try:
                await _delete_source_with_retries(client, notebook_id, source_id)
                deletion_error = None
            except Exception as delete_exc:
                deletion_error = str(delete_exc)
        attempt = SourceAttempt(
            attempt_index=attempt_index,
            report_id=report_id,
            source_kind=source_kind,
            remote_source_id=source_id,
            title=payload.get("title", ""),
            selected_for_analysis=False,
            ready=False,
            fulltext_path="",
            fulltext_sha256="",
            fulltext_char_count=0,
            fallback_reason=code,
            deleted_after_use=False,
            error=str(exc),
            deletion_error=deletion_error,
        )
        return attempt, [], False


def _to_request_file(settings: RuntimeSettings) -> Path:
    return settings.data_dir / "notebooklm" / "runtime-pass-request.json"


def run_policy_runtime_pass_via_worker(settings: RuntimeSettings) -> RuntimePassResult:
    ensure_runtime_locked(settings)
    request = _to_request_file(settings)
    response = settings.data_dir / "notebooklm" / "runtime-pass-result.json"
    request.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _safe_write_json(request, settings.to_request_payload(), redacted=False)

    root = Path(__file__).resolve().parents[3]
    command = [
        str(settings.venv_python),
        str(Path(__file__).resolve()),
        "--worker",
        "--request",
        str(request),
        "--result",
        str(response),
    ]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "backend")

    completed = subprocess.run(
        command,
        env=env,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "notebooklm worker failed").strip()
        raise _RuntimeWorkerError(err)
    data = json.loads(response.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise _RuntimeWorkerError("worker result is not a JSON object")
    return RuntimePassResult(**data)


async def run_policy_runtime_pass(settings: RuntimeSettings, *, use_inline: bool = False) -> RuntimePassResult:
    if settings.use_worker and not use_inline:
        return run_policy_runtime_pass_via_worker(settings)

    ensure_runtime_locked(settings)
    result = RuntimePassResult()
    selected_backend: str | None = None
    passed_backends: list[str] = []

    backend_probe_results: list[dict[str, Any]] = []
    for backend in settings.backend_candidates:
        probe = await _run_backend_probe(settings, backend)
        backend_probe_results.append(probe.as_dict())
        if probe.auth_ok and probe.upload_ok and probe.fulltext_ok and probe.ask_ok and probe.reset_ok and probe.error_code is None:
            passed_backends.append(backend)
    if passed_backends:
        if settings.backend_selection_preference in passed_backends:
            selected_backend = settings.backend_selection_preference
        else:
            selected_backend = passed_backends[0]
    result.backend_comparison = backend_probe_results

    if selected_backend is None:
        auth_candidates = [entry for entry in backend_probe_results if entry.get("error_code") == "AUTH_REQUIRED"]
        if auth_candidates:
            raise RuntimePassError("AUTH_REQUIRED", f"All backends denied auth: {json.dumps(auth_candidates, ensure_ascii=False, sort_keys=True)}")
        raise RuntimePassError("CHAT_RATE_LIMITED", "No backend passed Gate 0")
    result.selected_backend = selected_backend

    lock_path = settings.data_dir / settings.lock_name
    async with _acquire_workspace_lock(lock_path):
        async with _acquire_client(selected_backend, settings) as client:
            notebook_id, created = await _bind_or_create_notebook(client, settings, selected_backend)
            result.fixed_notebook_id = notebook_id
            result.fixed_notebook_created = created

            await _capacity_gate(client, notebook_id, settings)
            await _reset_workspace_health(client, notebook_id)
            result.source_count_before_cleanup = len(await _list_notebook_sources(client, notebook_id))
            result.conversation_state_before_cleanup = await _conversation_id(client, notebook_id)

            samples = [
                (
                    "PDF",
                    {
                        "title": "[QR-2026-09-03] Policy PDF｜量化测试机构｜2026-09-03",
                        "file_path": str(_sample_pdf_path(settings)),
                    },
                ),
                (
                    "WEIXIN_TEXT",
                    {
                        "title": f"{settings.sample_text_title}｜量化测试机构｜2026-09-03",
                        "text": settings.sample_text_body,
                    },
                ),
                (
                    "HTML_URL",
                    {
                        "title": "[QR-2026-09-03] Policy URL｜量化测试机构｜2026-09-03",
                        "url": _safe_validate_public_url(settings.sample_html_url),
                    },
                ),
            ]

            citation_records: list[dict[str, Any]] = []
            for idx, (kind, payload) in enumerate(samples, start=1):
                attempt, cites, _ = await _run_single_source_attempt(
                    client,
                    notebook_id,
                    settings,
                    kind,
                    payload,
                    attempt_index=idx,
                    report_id=20260903 + idx,
                    fulltext_dir=_fulltext_directory(settings),
                    timeout=settings.source_ready_timeout_seconds,
                )
                result.source_records.append(asdict(attempt))
                citation_records.extend(cites)
            result.citation_records = citation_records

            post_sources = await _list_notebook_sources(client, notebook_id)
            result.source_count_before_cleanup = len(post_sources)
            await _reset_workspace_health(client, notebook_id)
            final_sources = await _list_notebook_sources(client, notebook_id)
            result.source_count_after_cleanup = len(final_sources)
            result.conversation_state_after_cleanup = await _conversation_id(client, notebook_id)

    if result.source_count_after_cleanup != 0 or result.conversation_state_after_cleanup:
        raise RuntimePassError("SOURCE_DELETE_FAILED", "Cleanup did not produce empty workspace")

    if result.source_records and all(item["ready"] for item in result.source_records):
        result.status = "READY"
    else:
        result.status = "READY_CANDIDATE"
    result.error_code = "" if result.status == "READY" else "CITATION_MISSING"

    _safe_write_json(_evidence_path(settings), result.as_json(), redacted=False)
    write_operation_record(
        settings.data_dir,
        "notebooklm-policy-runtime-pass",
        {
            "goal": NOTEBOOKLM_RUNTIME_GOAL,
            "backend": result.selected_backend,
            "notebook_id": result.fixed_notebook_id,
            "status": result.status,
            "source_count_after_cleanup": result.source_count_after_cleanup,
            "evidence": str(_evidence_path(settings)),
        },
    )
    return result


def _run_worker_mode(request: Path, result: Path) -> int:
    request_payload = json.loads(request.read_text(encoding="utf-8"))
    settings = RuntimeSettings(
        data_dir=Path(request_payload["data_dir"]),
        profile_path=Path(request_payload["profile_path"]),
        venv_python=Path(request_payload["venv_python"]),
        backend_candidates=tuple(request_payload.get("backend_candidates", ("web", "android"))),
        backend_selection_preference=request_payload.get("backend_selection_preference", "web"),
        source_capacity_margin=int(request_payload.get("source_capacity_margin", 10)),
        historical_max_readable_sources=int(request_payload.get("historical_max_readable_sources", 0)),
        lock_name=request_payload.get("lock_name", "notebooklm-runtime-policy.lock"),
        evidence_name=request_payload.get("evidence_name", "notebooklm-runtime-pass-result.json"),
        sample_pdf_path=Path(request_payload["sample_pdf_path"]) if request_payload.get("sample_pdf_path") else None,
        sample_pdf_text=request_payload.get("sample_pdf_text", RuntimeSettings.sample_pdf_text),
        sample_text_title=request_payload.get("sample_text_title", RuntimeSettings.sample_text_title),
        sample_text_body=request_payload.get("sample_text_body", RuntimeSettings.sample_text_body),
        sample_html_url=request_payload.get("sample_html_url", RuntimeSettings.sample_html_url),
        capacity_gate_timeout_seconds=float(request_payload.get("capacity_gate_timeout_seconds", 900.0)),
        source_ready_timeout_seconds=float(request_payload.get("source_ready_timeout_seconds", 900.0)),
        ask_timeout_seconds=float(request_payload.get("ask_timeout_seconds", 120.0)),
        use_worker=bool(request_payload.get("use_worker", False)),
    )
    result_obj = asyncio.run(run_policy_runtime_pass(settings, use_inline=True))
    result.write_text(json.dumps(result_obj.as_json(), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true", help="Run in worker mode")
    parser.add_argument("--request", type=Path)
    parser.add_argument("--result", type=Path)
    return parser


def run_cli(argv: list[str] | None = None, settings: RuntimeSettings | None = None) -> RuntimePassResult | int:
    args = _build_parser().parse_args(argv)
    if args.worker:
        if args.request is None or args.result is None:
            raise RuntimeError("--worker requires --request and --result")
        return _run_worker_mode(args.request, args.result)
    runtime_settings = settings or RuntimeSettings.from_env(Path.cwd())
    try:
        result = asyncio.run(run_policy_runtime_pass(runtime_settings))
        print(json.dumps(result.as_json(), ensure_ascii=False, sort_keys=True))
        return result
    except RuntimePassError as exc:
        payload = {"goal": NOTEBOOKLM_RUNTIME_GOAL, "status": "FAILED", "error_code": exc.code, "error": exc.detail}
        raise RuntimeError(json.dumps(payload, ensure_ascii=False))


def _run_as_command() -> int:
    value = run_cli(sys.argv[1:])
    return 0 if isinstance(value, RuntimePassResult) else int(value)


if __name__ == "__main__":
    raise SystemExit(_run_as_command())
