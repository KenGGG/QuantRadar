# Research MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a standalone, idempotent daily research-report pipeline and its minimal verification UI.

**Architecture:** A Research-owned SQLAlchemy registry and local artifact store isolate report processing from the existing backtest schema. A synchronous CLI pipeline coordinates headless QYJ collection, PDF/MinerU processing, Agnes analysis, digest/outbox delivery, while FastAPI exposes only read-only status data.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, Pydantic, httpx, Playwright, React/TypeScript/Ant Design, systemd.

**Spec:** `docs/superpowers/specs/2026-08-25-research-mvp-design.md`

## Global Constraints

- Do not modify BulletTrade, Kronos runtime, `BacktestWorker`, or existing backtest storage.
- Do not persist credentials, cookies, PDF contents, Markdown, or API keys in Git.
- QYJ uses a separate headless persistent profile; authentication is diagnostic-only and never bypasses a CAPTCHA.
- MinerU uses the existing loopback API with concurrency one; no second MinerU or queue framework.
- Only PDFs enter parsing and analysis; non-PDF reports remain visible as unsupported metadata.
- Every production behavior begins with a failing unit test and ends with targeted plus relevant regression tests.

---

### Task 1: Configuration and independent storage

**Files:** Create `backend/quantradar/research/{config,models,storage}.py`, `tests/unit/research/{test_config,test_storage}.py`; modify `pyproject.toml`, `.env.example`.

**Interfaces:** `ResearchSettings.from_env() -> ResearchSettings`; `ResearchStore(settings).create_schema()`, `upsert_report()`, `record_snapshot()`, `begin_stage()`, `finish_stage()`, and `reserve_outbox()`.

- [ ] Write failing tests for local absolute data/profile validation, report identity uniqueness, multi-channel snapshots, idempotent successful stages, and unique notification keys.
- [ ] Run the focused tests and confirm the imports/functions are absent.
- [ ] Implement Pydantic settings, the seven independent SQLAlchemy models, and transactional store methods.
- [ ] Add Playwright as the only new application dependency and document non-secret environment variables.
- [ ] Run `pytest tests/unit/research/test_config.py tests/unit/research/test_storage.py -q` and commit `feat(research): add MVP storage and config`.

### Task 2: QYJ metadata collector

**Files:** Create `backend/quantradar/research/collector/{__init__,qyj}.py`, `tests/unit/research/test_qyj_collector.py`, and sanitized fixtures under `tests/fixtures/research/qyj/`.

**Interfaces:** `QyjCollector(settings, store).collect(target_date: date) -> CollectionResult`; `normalize_report(payload, channel, platform_order, target_date) -> NormalizedReport`.

- [ ] Write failing fixture-driven tests for stable IDs, `size/from` pagination without duplicates, multi-channel storage, order preservation, and authentication stop behavior.
- [ ] Run focused tests and confirm they fail before implementation.
- [ ] Implement headless persistent Chromium session, page-based transient header capture, three channel requests, pagination, raw JSON snapshots, and diagnostic failure artifacts.
- [ ] Run collector unit tests without contacting QYJ and commit `feat(research): collect qyj report metadata`.

### Task 3: PDF artifacts and MinerU parser

**Files:** Create `backend/quantradar/research/download/pdf.py`, `backend/quantradar/research/parser/{__init__,mineru,quality}.py`, and four unit-test files.

**Interfaces:** `PdfDownloader.download(report, attachment) -> PdfArtifactResult`; `MineruClient.parse(pdf_path, output_dir) -> ParseResult`; `assess_markdown(text) -> ParseQuality`.

- [ ] Write failing tests for atomic PDF writes, SHA dedupe, unsupported non-PDF reports, page-count mismatch warning, safe ZIP rejection, atomic Markdown publishing, and empty Markdown rejection.
- [ ] Run focused tests and confirm the missing behavior fails.
- [ ] Implement download validation using a PDF-aware parser, report-level non-fatal errors, MinerU health/request/retry logic, safe extraction, and quality metrics.
- [ ] Run parser/downloader tests and commit `feat(research): download and parse PDF artifacts`.

### Task 4: Agnes full-text analysis

**Files:** Create `backend/quantradar/research/llm/{__init__,base,agnes,chunking,schemas}.py`, prompt files, and analysis tests.

**Interfaces:** `plan_chunks(markdown, max_chars) -> list[SourceChunk]`; `AgnesProvider.analyze(...) -> dict`; `validate_analysis(analysis, chunks) -> ValidationResult`.

- [ ] Write failing tests for whole-report selection, deterministic long-report chunks preserving tail text, valid Market/Quant merges, retryable invalid JSON, evidence chunk existence, and numeric mismatch detection.
- [ ] Run the analysis tests and confirm they fail before implementation.
- [ ] Implement schema validation, token-safe section-first chunking, one Agnes provider, merge prompt, and evidence validator.
- [ ] Run analysis tests and commit `feat(research): analyze full reports with Agnes`.

### Task 5: Digest, Feishu outbox, and pipeline/CLI

**Files:** Create `digest/builder.py`, `notify/feishu.py`, `pipeline.py`, `cli.py`, systemd units, and digest/pipeline tests.

**Interfaces:** `DailyResearchPipeline.run(date) -> PipelineResult`; `DigestBuilder.build(date) -> DailyDigest`; `FeishuNotifier.send(digest) -> SendResult`.

- [ ] Write failing tests for coverage-first digest order, five-item limits, READY/PARTIAL/BLOCKED behavior, candidate selection limits, successful-stage rerun skips, auth stop, per-report failure isolation, and outbox duplicate prevention.
- [ ] Run targeted tests and confirm they fail before implementation.
- [ ] Implement deterministic candidate selection, pipeline stage checkpoints, digest builder, configured-keyword Feishu sender, commands `health`, `collect`, `daily`, and `resend`, plus the separate daily systemd timer.
- [ ] Run digest/pipeline tests and commit `feat(research): run daily research pipeline`.

### Task 6: Read-only API and Research verification UI

**Files:** Modify `backend/quantradar/api/app.py`, `frontend/src/{App,api}.tsx`; create `frontend/src/components/ResearchMVP.tsx`; add backend API tests and frontend build/typecheck coverage.

**Interfaces:** `GET /api/research/dates`, `/reports`, and `/status`; `getResearchDates()`, `getResearchReports()`, `getResearchStatus()`.

- [ ] Write failing backend tests for date ordering, channel/date report filtering, order preservation, unsupported content, and stage count aggregation.
- [ ] Run the backend tests and confirm the routes are absent.
- [ ] Implement only the three GET routes and a four-section Ant Design verification page with date selector, channel tabs, ordered title table, and pipeline status.
- [ ] Run API tests, `npm run typecheck`, `npm run build`, and commit `feat(research): add verification WebUI`.

### Task 7: Integration verification and operational handoff

**Files:** Create `tests/integration/research/test_daily_pipeline.py` and `docs/RESEARCH_MVP_IMPLEMENTATION_PLAN.md` as the maintained user-facing plan copy.

- [ ] Write a fixture-backed integration test demonstrating a rerunnable daily pipeline and a non-fatal per-report error.
- [ ] Run the integration test, all Research tests, existing unit tests, and frontend build.
- [ ] Run CLI health against the local MinerU service; use Gate 0 data only when credentials/configuration are available, recording results outside Git.
- [ ] Commit `test(research): validate MVP pipeline` and record that 30 samples, three dates, and seven unattended days remain acceptance operations rather than completed claims.
