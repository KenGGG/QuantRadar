# Kronos Goal 0 Data Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only, reproducible Goal 0 audit that produces the PRD-required data contract, evidence, and honest gates.

**Architecture:** A focused `quantradar.kronos.data_audit` package separates database inspection, evidence calculations, gate derivation, and atomic report publication. A thin CLI and Make target invoke the runner; no production Provider or BulletTrade behavior changes.

**Tech Stack:** Python 3.12, pandas, PyMySQL through `InvestmentDataConnection`, pytest, Dolt SQL.

**Spec:** `docs/superpowers/specs/2026-08-21-kronos-goal0-data-audit-design.md`

## Global Constraints

- Implement only Goal 0 and stop before Kronos runtime or strategy work.
- Query `/data/investment_data` read-only; never mutate or substitute data.
- Use deterministic samples of at least 30 stocks, 20 corporate-action candidates, and 20 PIT weeks when the source contains enough evidence.
- A changing Dolt HEAD fails the run before official reports are published.
- Missing evidence produces `PARTIAL` or `BLOCKED`, never fabricated `PASS`.

---

### Task 1: Core audit types and gate derivation

**Files:**
- Create: `backend/quantradar/kronos/__init__.py`
- Create: `backend/quantradar/kronos/data_audit/__init__.py`
- Create: `backend/quantradar/kronos/data_audit/models.py`
- Create: `backend/quantradar/kronos/data_audit/gates.py`
- Test: `tests/unit/kronos/test_data_audit_core.py`

**Interfaces:**
- Produces: `AuditStatus`, `GateEvidence`, `json_safe(value)`, `derive_data_gates(evidence)`.

- [ ] Write failing tests proving dates serialize to ISO strings and missing corporate-action evidence blocks formal/real-assist readiness.
- [ ] Run `pytest tests/unit/kronos/test_data_audit_core.py -q` and confirm missing-module failure.
- [ ] Implement immutable status/evidence types and explicit gate rules.
- [ ] Re-run the focused tests and confirm PASS.
- [ ] Commit `feat(kronos): add Goal 0 audit gate model`.

### Task 2: Schema, coverage, price, action, and PIT evidence collectors

**Files:**
- Create: `backend/quantradar/kronos/data_audit/schema.py`
- Create: `backend/quantradar/kronos/data_audit/prices.py`
- Create: `backend/quantradar/kronos/data_audit/actions.py`
- Create: `backend/quantradar/kronos/data_audit/universe.py`
- Test: `tests/unit/kronos/test_data_audit_collectors.py`

**Interfaces:**
- Consumes: `InvestmentDataConnection`, `InvestmentDataProvider`, audit models.
- Produces: `audit_schema_and_coverage`, `audit_price_semantics`, `audit_corporate_actions`, `audit_pit_universe`.

- [ ] Write failing tests with literal in-memory rows for factor formulas, deterministic sample size/category coverage, and snapshot-date selection.
- [ ] Verify RED with the focused test file.
- [ ] Implement minimal pure helpers, then SQL-backed collectors using parameterized SELECT queries only.
- [ ] Verify pure tests PASS.
- [ ] Add `requires_dolt` tests that assert real minimum sample counts and no future snapshot dates; run them against the local Dolt database.
- [ ] Commit `feat(kronos): collect Goal 0 audit evidence`.

### Task 3: Deterministic reports and atomic runner

**Files:**
- Create: `backend/quantradar/kronos/data_audit/report.py`
- Create: `backend/quantradar/kronos/data_audit/runner.py`
- Test: `tests/unit/kronos/test_data_audit_runner.py`

**Interfaces:**
- Consumes: collector outputs and `derive_data_gates`.
- Produces: `run_data_audit(connection, provider, output_dir) -> dict[str, object]`.

- [ ] Write failing tests proving all required filenames are produced, JSON dates are safe, and a changed ending Dolt HEAD prevents publication.
- [ ] Verify RED.
- [ ] Implement stable CSV/JSON/Markdown writers and staging-directory publication.
- [ ] Verify focused runner tests PASS.
- [ ] Commit `feat(kronos): publish deterministic Goal 0 reports`.

### Task 4: CLI, Make target, and real audit execution

**Files:**
- Create: `scripts/kronos_data_audit.py`
- Modify: `Makefile`
- Modify: `pyproject.toml`
- Test: `tests/unit/kronos/test_data_audit_cli.py`

**Interfaces:**
- Consumes: `run_data_audit` and existing bootstrap/configuration.
- Produces: `make kronos-data-audit` and CLI exit status 0 only for a completed audit.

- [ ] Write a failing CLI parser/entrypoint test that uses a temporary output directory.
- [ ] Verify RED.
- [ ] Add the thin CLI, pytest marker registration, and Make target.
- [ ] Run focused CLI tests, then `make kronos-data-audit` against the real database.
- [ ] Inspect generated artifacts for counts, dates, Dolt commit, and honest blocked gates.
- [ ] Commit `feat(kronos): add Goal 0 audit command`.

### Task 5: Phase documentation and verification

**Files:**
- Modify: `docs/ACTIVE_PHASE.md`
- Modify: `docs/CURRENT_STATE.md`
- Track: `reports/kronos/data_audit/*` by force-adding the small evidence artifacts required by the PRD.

**Interfaces:**
- Consumes: actual audit manifest and gate results.
- Produces: `KRONOS_DATA_CONTRACT_AUDIT_COMPLETE` with explicit non-PASS limitations.

- [ ] Update phase documents using only actual generated values and commands.
- [ ] Run Goal 0 focused tests and `git diff --check`.
- [ ] Re-run the real audit and compare manifest/output hashes where timestamps are excluded.
- [ ] Run the complete unit suite, recording the pre-existing baseline failures separately.
- [ ] Commit `docs(kronos): record Goal 0 audit evidence and gates`.
