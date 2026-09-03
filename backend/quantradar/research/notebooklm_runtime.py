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
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable
from urllib.error import HTTPError
from urllib.parse import parse_qs, urljoin, urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

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
MIN_INDEXED_CHARACTERS = 200
MAX_REDIRECTS = 5
WORKER_TIMEOUT_SECONDS = 1_200.0
WORKER_LOCK_TOKEN_ENV = "QUANTRADAR_NOTEBOOKLM_WORKER_LOCK_TOKEN"


def _long_non_sensitive_text(label: str) -> str:
    paragraph = (
        f"{label}。本材料为 QuantRadar NotebookLM 政策运行时的非敏感验收样本，"
        "不包含真实企业预警通内容、账户信息、投资建议或任何生产凭据。"
        "它用于验证 Source 上传、READY 状态、全文索引质量、显式 Source-ID 问答、"
        "引用身份映射、会话删除和 Source 删除的完整受控生命周期。"
        "样本中的事实均为测试用途：系统必须保留本地快照及哈希，在远端 Source 删除后"
        "仍能复核文本和引用。本段重复描述测试边界，以确保索引正文显著超过质量门槛。"
    )
    return "\n\n".join(paragraph for _ in range(5))


SAMPLE_PDF_TEXT = _long_non_sensitive_text("PDF 验收样本")
SAMPLE_TEXT_BODY = _long_non_sensitive_text("Text 验收样本")
SAMPLE_PROBE_TEXT = _long_non_sensitive_text("Backend 探针样本")
SAMPLE_CAPACITY_TEXT = _long_non_sensitive_text("容量探针样本")


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
    historical_max_readable_sources: int | None = None
    lock_name: str = "notebooklm-runtime-policy.lock"
    evidence_name: str = "notebooklm-runtime-pass-result.json"
    sample_pdf_path: Path | None = None
    sample_pdf_text: str = SAMPLE_PDF_TEXT
    sample_text_title: str = "QuantRadar NotebookLM Policy Runtime PASS"
    sample_text_body: str = SAMPLE_TEXT_BODY
    sample_html_url: str = "https://www.rfc-editor.org/rfc/rfc2606.html"
    capacity_gate_timeout_seconds: float = 900.0
    source_ready_timeout_seconds: float = 900.0
    ask_timeout_seconds: float = 120.0
    use_worker: bool = True
    source_capacity_probe_enabled: bool = True
    worker_timeout_seconds: float = WORKER_TIMEOUT_SECONDS

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
            source_capacity_margin=int(candidate_env.get("QUANTRADAR_NOTEBOOKLM_SOURCE_SAFETY_MARGIN", "10")),
            historical_max_readable_sources=_historical_max_daily_readable_unique_reports(),
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
            worker_timeout_seconds=float(candidate_env.get("QUANTRADAR_NOTEBOOKLM_WORKER_TIMEOUT", str(WORKER_TIMEOUT_SECONDS))),
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
    conversation_id: str | None = None
    error: str | None = None
    deletion_error: str | None = None


@dataclass
class CitationRecord:
    report_id: int
    expected_source_id: str
    actual_source_id: str
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
    pipeline_error_code: str | None = None
    pipeline_error_message: str | None = None
    cleanup_status: str = "NOT_STARTED"
    cleanup_error_code: str | None = None
    cleanup_error_message: str | None = None
    remaining_source_count: int | None = None
    remaining_conversation_id: str | None = None
    capacity_gate: dict[str, Any] = field(default_factory=dict)
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
    # Runtime evidence is always sanitized.  The flag is retained only for
    # compatibility with existing callers and intentionally cannot disable it.
    payload = _redact_for_log(payload)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = target.with_suffix(".part")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(target)
    os.chmod(target, 0o600)


def _atomic_write_text(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = target.with_suffix(".part")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(tmp, 0o600)
    tmp.replace(target)
    os.chmod(target, 0o600)


def _write_private_worker_json(target: Path, payload: dict[str, Any]) -> None:
    """Pass the profile path only through an owner-readable ephemeral Worker file."""
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = target.with_suffix(".part")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(target)
    os.chmod(target, 0o600)


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
    if isinstance(payload, str):
        value = re.sub(r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)[^\s;,]+", r"\1[REDACTED]", payload)
        value = re.sub(r"(?i)(bearer\s+)[^\s;,]+", r"\1[REDACTED]", value)
        value = re.sub(r"(?i)(cookie\s*[:=]\s*)[^\n;]+", r"\1[REDACTED]", value)
        value = re.sub(r"(?i)((?:master\s+)?token\s*[:=]\s*)[^\s;,]+", r"\1[REDACTED]", value)
        value = re.sub(r"(?i)(/[^\s\"']*(?:storage_state|credentials?|cookies?)[^\s\"']*)", "[REDACTED_PATH]", value)
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https"} and parsed.query:
            query = parse_qs(parsed.query, keep_blank_values=True)
            if any(key.lower() in SENSITIVE_URL_QUERY_KEYS for key in query):
                return urlunparse(parsed._replace(query="[REDACTED_QUERY]"))
        value = re.sub(r"(?i)(https?://[^\s?]+\?[^\s#]*(?:token|auth|signature|cookie)=[^\s&#]+)[^\s]*", "[REDACTED_URL]", value)
        return value
    return payload


def _build_retryable_delete(func: Callable[[], Awaitable[None]], exists_fn: Callable[[], Awaitable[bool]], *,
                          attempts: tuple[int, ...] = RETRY_ATTEMPTS, sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
                          ) -> Awaitable[None]:
    async def _runner() -> None:
        for delay in attempts:
            try:
                await func()
            except Exception as exc:
                if not _is_explicit_not_found(exc, "source") and not _is_explicit_not_found(exc, "conversation"):
                    raise
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
    if h in {"local", "qyj.cn", "qyj.com", "www.qyj.com", "qianyanjingji.com", "qyyjt.cn"} or h.endswith(".qyyjt.cn"):
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
        literal_ip = ipaddress.ip_address(host)
        if not _is_public_ip(literal_ip):
            raise RuntimePassError("HTML_URL_REJECTED", "URL uses a non-public IP address")
    except ValueError:
        pass
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
            if not _is_public_ip(ip):
                raise RuntimePassError("HTML_URL_REJECTED", "URL resolves to a non-public IP")
    except RuntimePassError:
        raise
    except OSError:
        raise RuntimePassError("HTML_URL_REJECTED", "URL DNS resolution failed")
    except Exception as exc:
        raise RuntimePassError("HTML_URL_REJECTED", f"URL host validation failed: {exc}")
    return url


def _is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    cgnat = isinstance(ip, ipaddress.IPv4Address) and ip in ipaddress.ip_network("100.64.0.0/10")
    return not any((ip.is_private, ip.is_loopback, ip.is_link_local, ip.is_reserved, ip.is_multicast, ip.is_unspecified, cgnat))


def _preflight_public_url(url: str) -> str:
    """Validate every hop locally before NotebookLM receives the public URL."""
    current = url
    opener = build_opener(_NoRedirect())
    for _ in range(MAX_REDIRECTS + 1):
        _safe_validate_public_url(current)
        try:
            with opener.open(Request(current, method="HEAD", headers={"User-Agent": "QuantRadar-NotebookLM-Policy"}), timeout=15) as response:
                return response.geturl()
        except HTTPError as exc:
            if exc.code not in {301, 302, 303, 307, 308}:
                raise RuntimePassError("HTML_URL_REJECTED", f"URL preflight returned HTTP {exc.code}") from exc
            location = exc.headers.get("Location")
            if not location:
                raise RuntimePassError("HTML_URL_REJECTED", "Redirect without Location") from exc
            current = urljoin(current, location)
    raise RuntimePassError("HTML_URL_REJECTED", "Too many URL redirects")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
        return None


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


def _extract_citations(
    report_id: int,
    expected_source_id: str,
    ask_result: Any,
    *,
    answer: str | None = None,
    ledger_source_ids: set[str] | None = None,
) -> list[CitationRecord]:
    refs = []
    for ref in getattr(ask_result, "references", []) or []:
        actual_source_id = str(getattr(ref, "source_id", "") or "")
        citation_number = getattr(ref, "citation_number", None)
        cited_text = str(getattr(ref, "cited_text", "") or "").strip()
        if not actual_source_id or actual_source_id not in (ledger_source_ids or {expected_source_id}):
            raise RuntimePassError("CITATION_SOURCE_MISMATCH", "Citation source is absent from the current Source ledger")
        if actual_source_id != expected_source_id:
            raise RuntimePassError("CITATION_SOURCE_MISMATCH", "Citation source does not match the requested Source")
        if not cited_text or citation_number is None or not str(getattr(ref, "chunk_id", "") or ""):
            raise RuntimePassError("CITATION_MISSING", "Citation is missing text, number, or chunk identity")
        if answer is not None and f"[{citation_number}]" not in answer:
            raise RuntimePassError("CITATION_MISSING", "Citation number is absent from the answer")
        refs.append(
            CitationRecord(
                report_id=report_id,
                expected_source_id=expected_source_id,
                actual_source_id=actual_source_id,
                citation_number=citation_number,
                cited_text=cited_text,
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
    path.write_bytes(_minimal_pdf_bytes(settings.sample_pdf_text))
    os.chmod(path, 0o600)
    return path


def _minimal_pdf_bytes(text: str) -> bytes:
    """Create a deterministic, structurally valid one-page PDF without a new dependency."""
    safe = re.sub(r"[^\x20-\x7e]", "?", _normalize_text(text))[:3_500]
    lines = [safe[offset : offset + 92] for offset in range(0, len(safe), 92)] or ["QuantRadar NotebookLM policy runtime sample"]
    content = "BT /F1 9 Tf 50 760 Td " + " ".join(f"({_pdf_escape(line)}) Tj 0 -12 Td" for line in lines[:54]) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(content.encode('latin-1'))} >>\nstream\n{content}\nendstream",
    ]
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n{obj}\nendobj\n".encode("latin-1"))
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    output.extend(b"".join(f"{offset:010d} 00000 n \n".encode("ascii") for offset in offsets[1:]))
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii"))
    return bytes(output)


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _sample_title(kind: str, report_id: int, settings: RuntimeSettings) -> str:
    labels = {"PDF": "Policy PDF", "WEIXIN_TEXT": "Policy Text", "HTML_URL": "Policy URL"}
    return f"[QR-{report_id}] {labels[kind]}｜量化测试机构｜2026-09-03"


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
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON object required")
    return payload


def _load_binding(settings: RuntimeSettings) -> dict[str, Any] | None:
    try:
        return _load_json_obj(_binding_path(settings))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimePassError("BINDING_CORRUPTED", "Fixed Notebook binding JSON is invalid") from exc


def _load_intent(settings: RuntimeSettings) -> dict[str, Any] | None:
    try:
        return _load_json_obj(_binding_intent_path(settings))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimePassError("BINDING_CORRUPTED", "Fixed Notebook recovery intent JSON is invalid") from exc


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
    except Exception as exc:
        if _is_explicit_not_found(exc, "conversation"):
            return None
        raise


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
    if current_cid:
        try:
            await _delete_conversation_with_retries(client, notebook_id)
            await _bounded_await(
                _conversation_absent,
                WORKSPACE_CONVERSATION_RESET_SECONDS,
                "Conversation reset timeout",
                interval=0.5,
            )
        except RuntimePassError as exc:
            raise RuntimePassError("CONVERSATION_RESET_FAILED", str(exc)) from exc


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
    if not content or len(content) < MIN_INDEXED_CHARACTERS:
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
    await _delete_conversation_with_retries(client, notebook_id)
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
            sources: list[Any] = []
            try:
                probe_samples = [
                    ("PDF", _sample_title("PDF", 20260901, settings), str(_sample_pdf_path(settings))),
                    ("WEIXIN_TEXT", _sample_title("WEIXIN_TEXT", 20260902, settings), SAMPLE_PROBE_TEXT),
                    ("HTML_URL", _sample_title("HTML_URL", 20260903, settings), _preflight_public_url(settings.sample_html_url)),
                ]
                results: dict[str, dict[str, Any]] = {}
                for kind, title, value in probe_samples:
                    if kind == "PDF":
                        source = await client.sources.add_file(notebook_id, value, title=title, wait=False)
                    elif kind == "WEIXIN_TEXT":
                        source = await client.sources.add_text(notebook_id, title, value, wait=False)
                    else:
                        source = await client.sources.add_url(notebook_id, value, title=title, wait=False)
                    sources.append(source)
                    ready_source = source if _source_is_ready(source) else await _wait_source_ready(client, notebook_id, source.id, timeout=settings.source_ready_timeout_seconds)
                    if not _source_is_ready(ready_source):
                        raise RuntimePassError("SOURCE_READY_TIMEOUT", f"{kind} probe did not become READY")
                    _, _, digest = await _fetch_fulltext(client, notebook_id, source.id)
                    ask_result, conversation_id = await _ask_with_explicit_source(
                        client, notebook_id, source.id, "这条样本是什么？", timeout_seconds=settings.ask_timeout_seconds
                    )
                    answer = str(getattr(ask_result, "answer", getattr(ask_result, "text", "")) or "")
                    citations = _extract_citations(20260900, source.id, ask_result, answer=answer or None, ledger_source_ids={source.id})
                    if not citations:
                        raise RuntimePassError("CITATION_MISSING", f"{kind} probe returned no citations")
                    results[kind] = {"ready": True, "fulltext_digest": digest, "citation_count": len(citations), "conversation_id": conversation_id}
                result.upload_ok = True
                result.fulltext_ok = True
                result.ask_ok = True
                result.details["sources"] = results
            finally:
                for source in sources:
                    try:
                        await _delete_source_with_retries(client, notebook_id, source.id)
                    except Exception as exc:
                        raise RuntimePassError("SOURCE_DELETE_FAILED", "Probe Source cleanup failed") from exc
                await client.notebooks.delete(notebook_id)
                try:
                    await client.notebooks.get(notebook_id)
                except Exception as exc:
                    if not _is_explicit_not_found(exc, "notebook"):
                        raise RuntimePassError("NOTEBOOK_DELETE_FAILED", "Probe Notebook deletion could not be verified") from exc
                else:
                    raise RuntimePassError("NOTEBOOK_DELETE_FAILED", "Probe Notebook remained after deletion")
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


async def _capacity_gate(client: Any, notebook_id: str, settings: RuntimeSettings) -> dict[str, int]:
    if not settings.source_capacity_probe_enabled:
        raise RuntimePassError("SOURCE_CAP_GATE_REQUIRED", "Capacity Gate is mandatory for NOTEBOOKLM_POLICY_RUNTIME_PASS")
    target = _capacity_target(settings)
    created: list[str] = []
    source_ids: list[str] = []
    try:
        for index in range(target):
            source = await client.sources.add_text(
                notebook_id,
                f"capacity-{index}",
                SAMPLE_CAPACITY_TEXT,
            )
            created.append(source.id)
            source_ids.append(source.id)
        ready_count = 0
        for source_id in source_ids:
            ready_source = await _wait_source_ready(client, notebook_id, source_id, timeout=settings.capacity_gate_timeout_seconds)
            if not _source_is_ready(ready_source):
                raise RuntimePassError("SOURCE_CAP_EXCEEDED", "Capacity Source did not reach READY")
            ready_count += 1
        for source_id in created:
            await _delete_source_with_retries(client, notebook_id, source_id)
        return {"historical_max": settings.historical_max_readable_sources or 0, "margin": settings.source_capacity_margin, "target": target, "ready_count": ready_count}
    except Exception as exc:
        for source_id in source_ids:
            try:
                await _delete_source_with_retries(client, notebook_id, source_id)
            except Exception:
                pass
        raise RuntimePassError("SOURCE_CAP_EXCEEDED", f"Capacity gate failed: {exc}") from exc


def _capacity_target(settings: RuntimeSettings) -> int:
    if settings.historical_max_readable_sources is None:
        raise RuntimePassError("SOURCE_CAP_HISTORY_UNAVAILABLE", "Historical readable Source peak is not available")
    if settings.historical_max_readable_sources < 0 or settings.source_capacity_margin < 0:
        raise RuntimePassError("SOURCE_CAP_HISTORY_UNAVAILABLE", "Historical peak and safety margin must be non-negative")
    return settings.historical_max_readable_sources + settings.source_capacity_margin


def _historical_max_daily_readable_unique_reports() -> int:
    """Compute capacity from persisted Snapshot membership and PARSE_OK artifacts."""
    try:
        from sqlalchemy import select
        from .config import ResearchSettings
        from .models import ResearchArtifact, ResearchReportSnapshot
        from .storage import ResearchStore

        store = ResearchStore(ResearchSettings.from_env())
        with store._session() as session:
            rows = session.execute(
                select(ResearchReportSnapshot.target_date, ResearchReportSnapshot.report_id, ResearchArtifact.parse_quality, ResearchArtifact.markdown_path)
                .join(ResearchArtifact, ResearchArtifact.report_id == ResearchReportSnapshot.report_id)
            ).all()
        daily: dict[Any, set[int]] = {}
        for target_date, report_id, quality, markdown_path in rows:
            if markdown_path and isinstance(quality, dict) and quality.get("status") == "PARSE_OK":
                daily.setdefault(target_date, set()).add(int(report_id))
        return max((len(report_ids) for report_ids in daily.values()), default=0)
    except Exception as exc:
        raise RuntimePassError("SOURCE_CAP_HISTORY_UNAVAILABLE", "Unable to calculate historical readable Source peak") from exc


def _is_explicit_not_found(exc: Exception, resource: str) -> bool:
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    return "notfound" in name or ("not found" in message and resource in message)


async def _bind_or_create_notebook(
    client: Any,
    settings: RuntimeSettings,
    backend: str,
) -> tuple[str, bool]:
    binding = _load_binding(settings) or {}
    binding_id = binding.get("notebook_id") if isinstance(binding, dict) else None

    if binding_id:
        try:
            notebook = await client.notebooks.get(binding_id)
            if getattr(notebook, "id", None) != binding_id:
                raise RuntimePassError("NOTEBOOK_BINDING_MISMATCH", "Saved Notebook ID did not round-trip")
            if str(getattr(notebook, "title", "")) != settings.notebook_title:
                raise RuntimePassError("NOTEBOOK_BINDING_MISMATCH", "Saved Notebook title no longer matches the fixed binding")
            return binding_id, False
        except Exception as exc:
            if isinstance(exc, RuntimePassError):
                raise
            if _is_explicit_not_found(exc, "notebook"):
                raise RuntimePassError("NOTEBOOK_MISSING", f"Saved notebook missing: {binding_id}") from exc
            raise

    intent = _load_intent(settings)
    if intent is not None:
        if intent.get("binding_key") != settings.binding_key or intent.get("notebook_title") != settings.notebook_title:
            raise RuntimePassError("NOTEBOOK_BINDING_MISMATCH", "Recovery intent does not match this fixed Notebook")

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

    # The intent remains durable across a timeout or unknown provider error.
    _save_intent(settings, "CREATE_NOTEBOOK", None, backend)
    try:
        created = await client.notebooks.create(settings.notebook_title)
        notebook_id = created.id
    except Exception as exc:
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
        _atomic_write_text(snapshot, content)

        await _delete_conversation_with_retries(client, notebook_id)
        ask_result, conversation_id = await _ask_with_explicit_source(
            client,
            notebook_id,
            source_id,
            "请给出这份材料的核心要点",
            timeout_seconds=settings.ask_timeout_seconds,
        )
        answer = str(getattr(ask_result, "answer", getattr(ask_result, "text", "")) or "")
        citations = _extract_citations(report_id, source_id, ask_result, answer=answer or None, ledger_source_ids={source_id})

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
            conversation_id=conversation_id,
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
            return attempt, citation_payload, False
        return attempt, citation_payload, True

    except RuntimePassError as exc:
        deleted_after_use = False
        if source_id:
            try:
                await _delete_source_with_retries(client, notebook_id, source_id)
                deletion_error = None
                deleted_after_use = True
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
            deleted_after_use=deleted_after_use,
            conversation_id=None,
            error=exc.detail,
            deletion_error=deletion_error,
        )
        return attempt, [], False
    except Exception as exc:
        code = _error_code_from_exception(exc)
        deleted_after_use = False
        if source_id:
            try:
                await _delete_source_with_retries(client, notebook_id, source_id)
                deletion_error = None
                deleted_after_use = True
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
            deleted_after_use=deleted_after_use,
            conversation_id=None,
            error=str(exc),
            deletion_error=deletion_error,
        )
        return attempt, [], False


def _worker_paths(settings: RuntimeSettings, run_id: str) -> tuple[Path, Path]:
    run_dir = settings.data_dir / "notebooklm" / "runtime" / run_id
    return run_dir / "request.json", run_dir / "result.json"


def _worker_environment(root: Path, worker_lock_token: str | None = None) -> dict[str, str]:
    allowed = {"LANG", "LC_ALL", "TZ"}
    env = {key: os.environ[key] for key in allowed if key in os.environ}
    env["PYTHONPATH"] = str(root / "backend")
    if worker_lock_token:
        env[WORKER_LOCK_TOKEN_ENV] = worker_lock_token
    return env


def run_policy_runtime_pass_via_worker(settings: RuntimeSettings) -> RuntimePassResult:
    try:
        ensure_runtime_locked(settings)
        lock_path = settings.data_dir / settings.lock_name
        with ResearchRunLock(lock_path):
            try:
                run_id = uuid.uuid4().hex
                request, response = _worker_paths(settings, run_id)
                request.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                worker_lock_token = uuid.uuid4().hex
                request_payload = settings.to_request_payload()
                request_payload["worker_lock_token"] = worker_lock_token
                _write_private_worker_json(request, request_payload)
                root = Path(__file__).resolve().parents[3]
                command = [str(settings.venv_python), str(Path(__file__).resolve()), "--worker", "--request", str(request), "--result", str(response)]
                completed = subprocess.run(command, env=_worker_environment(root, worker_lock_token), text=True, capture_output=True, timeout=settings.worker_timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                raise RuntimePassError("WORKER_TIMEOUT", "NotebookLM worker exceeded its bounded runtime") from exc
            if completed.returncode != 0:
                err = _redact_for_log((completed.stderr or completed.stdout or "notebooklm worker failed").strip())
                raise RuntimePassError("WORKER_FAILED", str(err))
            if not response.is_file():
                raise RuntimePassError("WORKER_FAILED", "worker did not produce a result file")
            data = json.loads(response.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise RuntimePassError("WORKER_FAILED", "worker result is not a JSON object")
            return RuntimePassResult(**data)
    except RuntimePassError as exc:
        _record_worker_failure(settings, exc)
        raise
    except Exception as exc:
        failure = RuntimePassError(_error_code_from_exception(exc), str(exc))
        _record_worker_failure(settings, failure)
        raise failure from exc


def _record_worker_failure(settings: RuntimeSettings, error: RuntimePassError) -> None:
    result = RuntimePassResult(status="FAILED", error_code=error.code, pipeline_error_code=error.code, pipeline_error_message=_redact_for_log(error.detail), cleanup_status="NOT_STARTED")
    _safe_write_json(_evidence_path(settings), result.as_json())
    write_operation_record(settings.data_dir, "notebooklm-policy-runtime-pass", {"goal": NOTEBOOKLM_RUNTIME_GOAL, "status": result.status, "error_code": error.code, "evidence": str(_evidence_path(settings))})


async def run_policy_runtime_pass(settings: RuntimeSettings, *, use_inline: bool = False, workspace_lock_held: bool = False) -> RuntimePassResult:
    if settings.use_worker and not use_inline:
        return run_policy_runtime_pass_via_worker(settings)

    try:
        ensure_runtime_locked(settings)
        if workspace_lock_held:
            return await _run_policy_runtime_pass_locked(settings)
        async with _acquire_workspace_lock(settings.data_dir / settings.lock_name):
            return await _run_policy_runtime_pass_locked(settings)
    except RuntimePassError as exc:
        _record_worker_failure(settings, exc)
        raise
    except Exception as exc:
        failure = RuntimePassError(_error_code_from_exception(exc), str(exc))
        _record_worker_failure(settings, failure)
        raise failure from exc


async def _run_policy_runtime_pass_locked(settings: RuntimeSettings) -> RuntimePassResult:
    result = RuntimePassResult()
    client: Any | None = None
    client_context: Any | None = None
    notebook_id: str | None = None
    primary_error: RuntimePassError | None = None
    cleanup_error: RuntimePassError | None = None
    try:
        probes = [await _run_backend_probe(settings, backend) for backend in settings.backend_candidates]
        result.backend_comparison = [probe.as_dict() for probe in probes]
        passed = [probe.backend for probe in probes if probe.auth_ok and probe.upload_ok and probe.fulltext_ok and probe.ask_ok and probe.reset_ok and probe.error_code is None]
        if not passed:
            codes = {probe.error_code for probe in probes}
            code = "AUTH_REQUIRED" if codes == {"AUTH_REQUIRED"} else next((probe.error_code for probe in probes if probe.error_code), "GATE0_BACKEND_FAILED")
            raise RuntimePassError(str(code), "No Backend passed the explicit Gate 0 comparison")
        result.selected_backend = settings.backend_selection_preference if settings.backend_selection_preference in passed else passed[0]
        client_context = _acquire_client(result.selected_backend, settings)
        client = await client_context.__aenter__()
        notebook_id, created = await _bind_or_create_notebook(client, settings, result.selected_backend)
        result.fixed_notebook_id, result.fixed_notebook_created = notebook_id, created
        await _reset_workspace_health(client, notebook_id)
        result.source_count_before_cleanup = len(await _list_notebook_sources(client, notebook_id))
        result.conversation_state_before_cleanup = await _conversation_id(client, notebook_id)
        result.capacity_gate = await _capacity_gate(client, notebook_id, settings)
        await _reset_workspace_health(client, notebook_id)
        samples = [("PDF", {"title": _sample_title("PDF", 20260904, settings), "file_path": str(_sample_pdf_path(settings))}), ("WEIXIN_TEXT", {"title": _sample_title("WEIXIN_TEXT", 20260905, settings), "text": settings.sample_text_body}), ("HTML_URL", {"title": _sample_title("HTML_URL", 20260906, settings), "url": _preflight_public_url(settings.sample_html_url)})]
        for idx, (kind, payload) in enumerate(samples, start=1):
            attempt, citations, succeeded = await _run_single_source_attempt(client, notebook_id, settings, kind, payload, attempt_index=idx, report_id=20260903 + idx, fulltext_dir=_fulltext_directory(settings), timeout=settings.source_ready_timeout_seconds)
            result.source_records.append(asdict(attempt))
            result.citation_records.extend(asdict(item) for item in citations)
            if not succeeded:
                raise RuntimePassError(attempt.fallback_reason or "SOURCE_UPLOAD_FAILED", attempt.error or "Source attempt failed")
    except RuntimePassError as exc:
        primary_error = exc
    except Exception as exc:
        primary_error = RuntimePassError(_error_code_from_exception(exc), str(exc))
    finally:
        if client is not None and notebook_id is not None:
            try:
                await _reset_workspace_health(client, notebook_id)
                result.remaining_source_count = len(await _list_notebook_sources(client, notebook_id))
                result.remaining_conversation_id = await _conversation_id(client, notebook_id)
                result.source_count_after_cleanup = result.remaining_source_count
                result.conversation_state_after_cleanup = result.remaining_conversation_id
                if result.remaining_source_count != 0 or result.remaining_conversation_id:
                    raise RuntimePassError("NOTEBOOK_DIRTY", "Cleanup verification found residual workspace state")
                result.cleanup_status = "PASS"
            except Exception as exc:
                cleanup_error = exc if isinstance(exc, RuntimePassError) else RuntimePassError(_error_code_from_exception(exc), str(exc))
                result.cleanup_status = "FAILED"
                result.cleanup_error_code = cleanup_error.code
                result.cleanup_error_message = _redact_for_log(cleanup_error.detail)
        else:
            result.cleanup_status = "NOT_APPLICABLE"
        if client_context is not None:
            try:
                await client_context.__aexit__(None, None, None)
            except Exception as exc:
                cleanup_error = RuntimePassError(_error_code_from_exception(exc), str(exc))
                result.cleanup_status = "FAILED"
                result.cleanup_error_code = cleanup_error.code
                result.cleanup_error_message = _redact_for_log(cleanup_error.detail)
        if primary_error is not None:
            result.pipeline_error_code, result.pipeline_error_message = primary_error.code, _redact_for_log(primary_error.detail)
        if primary_error is None and cleanup_error is None and len(result.source_records) == 3 and all(item["ready"] and item["deleted_after_use"] for item in result.source_records):
            result.status, result.error_code = "READY", None
        else:
            result.status = "FAILED"
            result.error_code = primary_error.code if primary_error is not None else (cleanup_error.code if cleanup_error is not None else "SOURCE_UPLOAD_FAILED")
        _safe_write_json(_evidence_path(settings), result.as_json())
        write_operation_record(settings.data_dir, "notebooklm-policy-runtime-pass", {"goal": NOTEBOOKLM_RUNTIME_GOAL, "backend": result.selected_backend, "notebook_id": result.fixed_notebook_id, "status": result.status, "error_code": result.error_code, "cleanup_status": result.cleanup_status, "source_count_after_cleanup": result.source_count_after_cleanup, "evidence": str(_evidence_path(settings))})
    return result


def _run_worker_mode(request: Path, result: Path) -> int:
    request_payload = json.loads(request.read_text(encoding="utf-8"))
    worker_lock_token = request_payload.pop("worker_lock_token", None)
    if not worker_lock_token or worker_lock_token != os.environ.get(WORKER_LOCK_TOKEN_ENV):
        raise RuntimePassError("WORKER_LOCK_OWNERSHIP_INVALID", "Worker may run only under the parent workspace lock")
    settings = RuntimeSettings(
        data_dir=Path(request_payload["data_dir"]),
        profile_path=Path(request_payload["profile_path"]),
        venv_python=Path(request_payload["venv_python"]),
        backend_candidates=tuple(request_payload.get("backend_candidates", ("web", "android"))),
        backend_selection_preference=request_payload.get("backend_selection_preference", "web"),
        source_capacity_margin=int(request_payload.get("source_capacity_margin", 10)),
        historical_max_readable_sources=(int(request_payload["historical_max_readable_sources"]) if request_payload.get("historical_max_readable_sources") is not None else None),
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
        source_capacity_probe_enabled=bool(request_payload.get("source_capacity_probe_enabled", True)),
        worker_timeout_seconds=float(request_payload.get("worker_timeout_seconds", WORKER_TIMEOUT_SECONDS)),
    )
    result_obj = asyncio.run(run_policy_runtime_pass(settings, use_inline=True, workspace_lock_held=True))
    _safe_write_json(result, result_obj.as_json())
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
