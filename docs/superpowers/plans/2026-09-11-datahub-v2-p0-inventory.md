# DataHub V2 P0 Inventory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a fixed-release inventory that distinguishes reusable base material, true gaps, and quarantined supplemental data before any new collection is scheduled.

**Architecture:** Add one read-only inventory service beside the existing DataHub coordinator. It discovers actual base tables at the release's pinned Dolt commit, records field-level coverage and source evidence, and creates a strategy-window gap plan. The existing coordinator, release reader, journal, and Governor remain the only runtime systems.

**Tech Stack:** Python 3.12, PyMySQL, Dolt, existing DataHub JSON artifacts, pytest.

**Spec:** `/home/ken/下载/QuantRadar_DataHub_历史复用与渐进补数_实施方案_v2.md`

## Global Constraints

- Read base and supplemental data only through the release-pinned commits.
- Do not request Tushare credentials, write base tables, reset Dolt, delete raw material, or change old release semantics.
- Record `VALID`, `VALID_NULL`, `NOT_APPLICABLE`, `MISSING`, `QUARANTINED`, and `UNKNOWN` separately.
- Treat `000300.SH` and `399300.SZ` as unrelated until identity and overlapping effective periods are proven.
- Preserve the 196 failed and 123 unverified valuation records as quarantined evidence.

---

### Task 1: Fixed-release base inventory

**Files:**
- Create: `backend/quantradar/datahub/inventory.py`
- Modify: `backend/quantradar/datahub/service.py`
- Test: `tests/unit/test_datahub_inventory.py`

**Interfaces:**
- Produces `BaseInventory.scan(scope) -> dict` with `base_commit`, `tables`, `domains`, and `generated_at`.
- Each domain reports table, fields, source evidence, units, first/last date, stock count, row count, continuous intervals, and internal-gap summary.

- [ ] **Step 1: Write failing tests** for schema discovery and domain classification using a fake read-only connection that exposes `final_a_stock_eod_price`, `ts_a_stock_eod_price`, `bao_a_stock_eod_info`, and `ts_a_stock_list`.
- [ ] **Step 2: Run** `PYTHONPATH=backend .venv/bin/pytest -q tests/unit/test_datahub_inventory.py` and verify the import fails because `inventory.py` does not exist.
- [ ] **Step 3: Implement** the smallest scanner that uses `information_schema`, `SHOW COLUMNS`, and aggregate `SELECT` statements. Classify final price, source price, status, lifecycle, calendar, and index-weight domains from discovered tables only.
- [ ] **Step 4: Run** the unit test and verify it passes.
- [ ] **Step 5: Add** `DataHubService.base_inventory(release_id=None)` which resolves a release once and writes `base_inventory.json` under the supplemental repository using atomic JSON replacement.
- [ ] **Step 6: Run** the unit test and the existing DataHub unit suite.

### Task 2: Index identity and source contracts

**Files:**
- Create: `backend/quantradar/datahub/source_contracts.yaml`
- Modify: `backend/quantradar/datahub/inventory.py`
- Test: `tests/unit/test_datahub_inventory.py`

**Interfaces:**
- Produces `index_aliases` entries with `status` of `VALID`, `UNKNOWN`, or `CONFLICT` and evidence fields; no automatic alias is emitted for a failed comparison.
- Produces `source_contracts` entries keyed by source-contract ID, each with actual upstream, allowed fields, unit conversion, health, and evidence requirement.

- [ ] **Step 1: Write failing tests** showing that non-overlapping or different constituent samples for `000300.SH` and `399300.SZ` return `UNKNOWN`, while a verified same-identity overlap returns a versioned alias.
- [ ] **Step 2: Run** the focused test and verify failure.
- [ ] **Step 3: Implement** exact-code aggregation and overlapping constituent-set comparison; do not derive aliases from suffix replacement.
- [ ] **Step 4: Add** contracts for base `final`, base `ts`, base `bao`, Eastmoney valuation, AKShare Tencent raw price candidate, and frozen BaoStock candidate. Mark unverified network routes `UNKNOWN`/`FROZEN`, not usable.
- [ ] **Step 5: Run** focused tests and verify pass.

### Task 3: Strategy-window gap plan

**Files:**
- Modify: `backend/quantradar/datahub/inventory.py`
- Modify: `backend/quantradar/datahub/daily.py`
- Test: `tests/unit/test_datahub_inventory.py`

**Interfaces:**
- Produces `gap_plan(strategy_window, scope) -> dict` with `current_update`, `strategy_gap`, and `historical_repair` queues.
- Every work item has source contract, domain/field group, symbols, date range, cause, original fingerprint, budget state, and status.

- [ ] **Step 1: Write failing tests** proving a valid base raw table resolves a final-table hole without a network item, while a missing status range produces an `UNKNOWN` work item.
- [ ] **Step 2: Run** the focused test and verify failure.
- [ ] **Step 3: Implement** range merging with a one-day boundary-check window and idempotency keys containing contract, fields, symbols, range, and source fingerprint.
- [ ] **Step 4: Make** `DailyUpdate.run` call the planner before fetch selection and persist `gap_plan.json`; existing valuation jobs remain unchanged until a source contract is qualified.
- [ ] **Step 5: Run** focused and existing DataHub suites.

### Task 4: Real P0 evidence and UI wording

**Files:**
- Modify: `backend/quantradar/api/app.py`
- Modify: `frontend/src/components/DataStatus.tsx`
- Modify: `docs/datahub-contract.md`
- Create: `docs/acceptance/datahub-v2-p0/README.md`
- Test: `tests/unit/test_datahub_inventory.py`, `tests/unit/test_datahub_remediation.py`

**Interfaces:**
- Overview exposes `base_inventory`, `source_contracts`, and `gap_plan` from saved artifacts; page labels physical storage and actual upstream separately.

- [ ] **Step 1: Write a failing API test** for separate `base_contribution`, `supplemental_contribution`, `remaining_gap`, and source-health output.
- [ ] **Step 2: Run** the test and verify failure.
- [ ] **Step 3: Implement** saved-artifact API output and simplify the page into coverage, source contribution, and unresolved gaps without treating generic download counts as published coverage.
- [ ] **Step 4: Run** backend tests, frontend typecheck/build, and browser smoke test.
- [ ] **Step 5: Run** the inventory against the real fixed release; store only non-sensitive aggregate evidence and document true versus false gaps.

