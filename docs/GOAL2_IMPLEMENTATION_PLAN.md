# Kronos Goal 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the reproducible research-only pipeline `investment_data -> locked Kronos-base -> Signal Artifact -> TopK Target Weight -> BulletTrade native report` and earn `GOAL2_ENGINEERING_PASS`.

**Architecture:** QuantRadar builds and stores PIT inputs without Torch, an offline CUDA subprocess emits five deterministic prediction paths, and pure adapters produce signals and weights. A generic target-weight strategy calls the existing `run_unified_backtest`; manifests link every report back to weights, signals, predictions, inputs, the Dolt commit, and immutable model revisions.

**Tech Stack:** Python 3.12, pandas, NumPy, Parquet, Dolt/MySQL provider, isolated PyTorch/CUDA Kronos runtime, BulletTrade 0.9.2, pytest.

**Spec:** `docs/superpowers/specs/2026-08-21-kronos-investment-workbench-goal2-design.md`

## Global Constraints

- The QuantRadar process must never import Torch; model inference remains in `.venv-kronos`.
- The exact Goal 1 model, tokenizer, source revisions, five seeds, CUDA-only policy, and offline environment remain locked.
- `run_unified_backtest()` is the only backtest/report implementation; do not recreate matching, metrics, accounting, or reports.
- `formal_backtest_ready` and `real_assist_data_ready` remain `false`.
- No WebUI, parameter matrix, fine-tuning, live/shadow trading, or supplement ETL.
- Every behavior change follows RED-GREEN-REFACTOR and every completed task is committed.

---

### Task 1: Prediction-to-Signal Adapter

**Files:**
- Create: `backend/quantradar/kronos/signal/__init__.py`
- Create: `backend/quantradar/kronos/signal/adapter.py`
- Test: `tests/unit/kronos/test_signal_adapter.py`

**Interfaces:**
- Consumes: `predictions: np.ndarray[path, symbol, horizon, feature]`, symbols, signal metadata.
- Produces: `build_signals(...) -> pd.DataFrame` with the PRD schema and deterministic ranks; `prediction_content_hash(...) -> str`.

- [x] Write literal-fixture tests for median return, q10/q50/q90, up probability, population standard deviation, invalid paths, and symbol tie-breaks.
- [x] Run `PYTHONPATH=backend .venv/bin/python -m pytest tests/unit/kronos/test_signal_adapter.py -q` and verify missing-module failure.
- [x] Implement validation, per-path `close[-1] / open[0] - 1`, stable sorting, audit columns, and SHA-256 hashing without Torch.
- [x] Re-run the adapter tests and commit `feat(kronos): add deterministic signal adapter`.

### Task 2: Reproducible Signal Artifact Store

**Files:**
- Create: `backend/quantradar/kronos/signal/manifest.py`
- Create: `backend/quantradar/kronos/signal/store.py`
- Test: `tests/unit/kronos/test_signal_store.py`

**Interfaces:**
- Consumes: config/model/data fingerprints, a completed weekly signal frame, input and prediction files.
- Produces: deterministic `signal_run_id`, atomic `weeks/YYYY-MM-DD`, validated resume state, merged `signals.parquet`, `progress.json`, and root `manifest.json`.

- [x] Write failing tests that commit one real temp-directory partition, resume it, reject a changed config, and reject a tampered artifact.
- [x] Implement canonical JSON hashing, file hashing, atomic JSON/Parquet writes, partition manifests, validation, and root merge.
- [x] Run store plus adapter tests and commit `feat(kronos): add resumable signal artifact store`.

### Task 3: PIT Weekly Inputs and CUDA Prediction Contract

**Files:**
- Create: `backend/quantradar/kronos/signal/inputs.py`
- Create: `backend/quantradar/kronos/signal/subprocess_runner.py`
- Create: `kronos_runtime/signal_runner.py`
- Modify: `kronos_runtime/runner.py`
- Test: `tests/unit/kronos/test_signal_inputs.py`
- Test: `tests/unit/kronos/test_signal_subprocess.py`

**Interfaces:**
- Produces `list_signal_dates(provider, start, end)`, `collect_week_input_package(...)`, and `run_signal_subprocess(...)`.
- Runtime output contains `predictions.npz` with `predictions[path,symbol,10,6]` and a JSON result whose hashes are independently verified by the caller.

- [x] Write failing pure/fake-connection tests for weekly dates, explicit PIT date, T+1 execution date, 90 rows, stable input hash, offline command, and malformed output rejection.
- [x] Reuse the locked prediction helpers from the Goal 1 runner without changing its output and implement the dedicated signal runner.
- [x] Implement main-process command/result validation and input packaging with Dolt HEAD checks before and after each week.
- [x] Run Goal 1 runtime regressions and new contract tests; commit `feat(kronos): add weekly PIT prediction runtime`.

### Task 4: TopK Portfolio and Generic Target-Weight Bridge

**Files:**
- Create: `backend/quantradar/kronos/portfolio.py`
- Create: `backend/quantradar/portfolio/__init__.py`
- Create: `backend/quantradar/portfolio/target_weight_bridge.py`
- Modify: `backend/quantradar/qml/bridge.py`
- Test: `tests/unit/kronos/test_kronos_portfolio.py`
- Test: `tests/unit/test_target_weight_bridge.py`
- Modify: `tests/unit/test_bridge.py`

**Interfaces:**
- Produces `build_topk_target_weights(signals, topk=20)` long and wide weights and a deterministic weight hash.
- Produces strategy source for `weekly` or `monthly`; Qlib delegates with its unchanged monthly default.

- [x] Write failing tests for TopK, deterministic ties, fewer-than-K, row sum 1, `execution_date > signal_date`, weekly scheduling, and same-day execution-date eligibility without same-day signal leakage.
- [x] Implement pure portfolio conversion and the generic strategy-source builder.
- [x] Make Qlib delegate to the generic bridge while preserving its public API and existing tests.
- [x] Run portfolio/bridge regressions; the long real Qlib loop is included in final regression, then commit `feat(kronos): bridge weekly target weights to BulletTrade`.

### Task 5: Pipeline Orchestrator, Audit Chain, and CLI

**Files:**
- Create: `backend/quantradar/kronos/pipeline.py`
- Create: `scripts/kronos_research_pipeline.py`
- Modify: `Makefile`
- Test: `tests/unit/kronos/test_pipeline.py`
- Test: `tests/unit/kronos/test_pipeline_cli.py`

**Interfaces:**
- `run_research_pipeline(...) -> dict` builds/resumes weeks, writes weights, calls `run_unified_backtest`, copies signal/strategy locks into the run, and writes `kronos_research_manifest.json`.
- CLI returns 0 only when engineering artifacts validate, otherwise nonzero with a JSON reason.

- [ ] Write failing orchestration tests with real temp artifacts and injected slow boundaries, asserting report-to-prediction hash traversal and false formal/assist gates.
- [ ] Implement orchestration, strategy lock, attachment of signal files to the BulletTrade run directory, and engineering gate evaluation.
- [ ] Implement CLI arguments and `kronos-research-pipeline` Make target; test success and failure exit codes.
- [ ] Run all Goal 2 unit/integration tests and commit `feat(kronos): orchestrate research pipeline CLI`.

### Task 6: Real Environment Acceptance

**Files:**
- Create at runtime: `artifacts/kronos/signals/<signal_run_id>/...`
- Create at runtime: `runs/<run_id>/...`
- Create: `reports/kronos/goal2_engineering/engineering_gate.json`
- Create: `reports/kronos/goal2_engineering/acceptance_manifest.json`

- [ ] Run one real Dolt/PIT week through locked Kronos-base CUDA and verify prediction hashes by repeating it.
- [ ] Run a real multi-week signal/weight/BulletTrade chain over the smallest valid range that produces trades and an HTML report.
- [ ] Validate every manifest/file hash, `execution_date > signal_date`, weight sums, unchanged Dolt commit, native BulletTrade reports, and both closed data gates.
- [ ] Commit compact evidence manifests (not large model/prediction/report binaries) as `test(kronos): record Goal 2 real acceptance`.

### Task 7: Regression, Documentation, and Delivery

**Files:**
- Modify: `docs/ACTIVE_PHASE.md`
- Modify: `docs/CURRENT_STATE.md`
- Modify: `docs/GOAL2_IMPLEMENTATION_PLAN.md`

- [ ] Run the complete Kronos suite, affected bridge/backtest suites, and the full unit suite; distinguish new failures from the recorded 15 pre-existing date-serialization failures.
- [ ] Mark every completed checkbox, document exact commands/counts/timings and `GOAL2_ENGINEERING_PASS` only if all ten completion conditions are true.
- [ ] Use verification-before-completion and finishing-a-development-branch, commit documentation, inspect the final diff, and attempt a non-force push of the current feature branch.
