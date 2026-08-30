# Yesterday Three-Channel Digest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Produce a versioned, idempotent yesterday Digest that accounts for every Snapshot in HOT, STRATEGY, and FINANCIAL_ENGINEERING and synthesizes each channel independently.

**Architecture:** `ResearchReportSnapshot(target_date, channel)` becomes the single membership source. A new analysis profile produces richer evidence-backed report analysis; a channel-synthesis adapter consumes only those structured analyses. The digest stores a complete structured payload plus WebUI/Feishu Markdown, and changes its hash when membership, analyses, or profile change.

**Tech Stack:** Python 3.12, SQLAlchemy, FastAPI, Agnes HTTP adapter, React/Ant Design, pytest.

**Spec:** User-approved `REPORT_MVP_YESTERDAY_DIGEST_PASS` requirements of 2026-08-30, with the explicit correction that the third channel is `FINANCIAL_ENGINEERING`, not `FIXED_INCOME`.

## Global Constraints

- Formal channel order is `HOT`, `STRATEGY`, `FINANCIAL_ENGINEERING` only.
- Preserve QYJ parameters `hotReport=1`, `10301,10302,10303`, and `10202,10203` exactly.
- No merge, no timer enablement, and no seven-day observation before real 2026-08-29 acceptance.
- Synthesis receives structured, validated report analyses only; it never receives concatenated original Markdown.
- Digest membership, counts, order, and exception accounting derive from Snapshot rows.

### Task 1: Lock channel and Snapshot membership contracts

**Files:** `tests/unit/research/test_qyj_collector.py`, `tests/unit/research/test_delivery.py`, `backend/quantradar/research/storage.py`.

- [ ] Add failing tests for all three exact QYJ parameter maps, Snapshot membership, duplicate membership across channels, and platform ordering.
- [ ] Run the focused tests and observe failure against legacy Digest.
- [ ] Add read-only Snapshot-scoped store query returning every member plus its current artifact, analysis, and latest stage status.
- [ ] Verify the focused tests pass and commit the isolated contract.

### Task 2: Upgrade report analysis profile and schema

**Files:** `tests/unit/research/test_analysis_validation.py`, `tests/unit/research/test_analysis_service.py`, `backend/quantradar/research/analysis.py`, `backend/quantradar/research/llm/agnes.py`, `backend/quantradar/research/llm/schemas.py`.

- [ ] Add failing validation tests for `key_points`, `core_conclusion`, `method_or_logic`, and `risks_or_limitations`.
- [ ] Bump prompt/schema profile and require the fields while retaining Evidence validation.
- [ ] Verify profile changes prevent stale analysis reuse and all analysis tests pass.

### Task 3: Build channel synthesis and versioned Digest

**Files:** `tests/unit/research/test_delivery.py`, `backend/quantradar/research/delivery.py`, `backend/quantradar/research/models.py`, `backend/quantradar/research/storage.py`.

- [ ] Add failing tests for independent channel synthesis, full accounting, failure visibility, digest version invalidation, idempotent same-input reuse, and changed input hash regeneration.
- [ ] Add additive Digest version/profile storage support.
- [ ] Build bounded channel synthesis requests from deterministic structured-analysis batches and render the complete JSON and Markdown formats.
- [ ] Keep historical Outbox rows; make new delivery content a concise three-channel Feishu summary.
- [ ] Verify focused delivery tests pass.

### Task 4: Expose and render complete channel Digests

**Files:** `tests/unit/research/test_research_api.py`, `backend/quantradar/api/app.py`, `frontend/src/api.ts`, `frontend/src/components/ResearchMVP.tsx`.

- [ ] Add failing API/UI-contract tests for complete versioned content JSON and the three formal channel names.
- [ ] Return safe complete Digest JSON and render channel cards, synthesis, article index, and exceptions in the existing read-only WebUI.
- [ ] Run frontend typecheck/build and API tests.

### Task 5: Run real 2026-08-29 acceptance and update state

**Files:** `docs/ACTIVE_PHASE.md`, `docs/CURRENT_STATE.md`, ignored runtime acceptance evidence.

- [ ] Collect each live QYJ channel for 2026-08-29 and record parameter, upstream/persisted counts, unique IDs, order bounds, title samples.
- [ ] Prepare/analyze the required channel members with the new profile, generate actual channel synthesis and Digest, and perform six report Evidence checks.
- [ ] Run Feishu dry-run only, all backend/Research/frontend verification, `git diff --check`, commit and push.
- [ ] Mark the Goal PASS only after all evidence exists; create a PR but do not merge unless separately authorized.
