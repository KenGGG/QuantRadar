# Kronos Goal 1 Runtime and GPU Smoke Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify an immutable, CUDA-only Kronos-base runtime with real 1-stock, 50-stock, full-PIT one-path, and full-PIT five-path benchmarks.

**Architecture:** QuantRadar prepares a real, hashed NumPy package without Torch and calls a standalone Python runtime in `.venv-kronos`. Setup may access the network, while lock verification and smoke inference are offline and reject any source, model, environment, or CUDA mismatch.

**Tech Stack:** Python 3.12, NumPy, pandas, PyTorch CUDA, Hugging Face Hub, safetensors, InvestmentDataProvider, pytest.

**Spec:** `docs/superpowers/specs/2026-08-21-kronos-goal1-runtime-design.md`

## Global Constraints

- Do not implement signals, portfolios, backtests, API, or WebUI.
- Main QuantRadar code must not import Torch.
- Never fall back from `Kronos-base` to another model or from CUDA to CPU.
- Normal smoke execution must be offline and use immutable local snapshots.
- Read `/data/investment_data` through read-only provider operations only.
- Keep Goal 0 research and trading gates unchanged.

---

### Task 1: Runtime contracts and gate

**Files:**
- Create: `backend/quantradar/kronos/runtime/contracts.py`
- Create: `backend/quantradar/kronos/runtime/gates.py`
- Create: `backend/quantradar/kronos/runtime/__init__.py`
- Test: `tests/unit/kronos/test_runtime_contracts.py`

**Interfaces:**
- Produces: immutable identifiers, `BenchmarkStage`, and `evaluate_runtime_gate(result) -> dict`.

- [ ] Write tests that fail because the contracts and gate do not exist.
- [ ] Run `PYTHONPATH=backend .venv/bin/python -m pytest tests/unit/kronos/test_runtime_contracts.py -q` and confirm the expected import failure.
- [ ] Implement strict constants, result validation, and a gate that requires all four real CUDA stages plus determinism.
- [ ] Re-run the test and commit the passing task.

### Task 2: Real PIT benchmark package

**Files:**
- Create: `backend/quantradar/kronos/runtime/inputs.py`
- Test: `tests/unit/kronos/test_runtime_inputs.py`
- Test: `tests/unit/kronos/test_runtime_inputs_live.py`

**Interfaces:**
- Consumes: `InvestmentDataProvider`, Goal 0 contract, and read-only Dolt queries.
- Produces: `build_runtime_input_package(output_dir) -> dict` and a hashed NPZ package.

- [ ] Write failing pure tests for eligibility, qfq anchoring, deterministic ordering, exclusions, and package hashes.
- [ ] Implement pure selection and package serialization, then make pure tests pass.
- [ ] Write a failing `requires_dolt` test for the real latest PIT snapshot and 90-day package.
- [ ] Implement the read-only collector and make the live test pass.
- [ ] Commit the input package task.

### Task 3: Offline model lock

**Files:**
- Create: `kronos_runtime/model_lock.py`
- Create: `kronos_runtime/requirements.lock`
- Create: `scripts/setup_kronos_runtime.py`
- Test: `tests/unit/kronos/test_model_lock.py`

**Interfaces:**
- Produces: exact local source/snapshot installation and `models/kronos/kronos_model_lock.json`.

- [ ] Write failing tests for complete SHA256 coverage, immutable revisions, source commit mismatch, and CUDA requirement.
- [ ] Implement deterministic hashing and lock validation without downloading during verification.
- [ ] Add setup behavior that creates `.venv-kronos`, installs exact dependencies, checks out the exact source, downloads exact revisions, and generates the lock.
- [ ] Make tests pass and commit.

### Task 4: CUDA-only standalone runner and parent subprocess

**Files:**
- Create: `kronos_runtime/runner.py`
- Create: `backend/quantradar/kronos/runtime/subprocess_runner.py`
- Test: `tests/unit/kronos/test_runtime_runner.py`

**Interfaces:**
- Consumes: locked source/snapshots and runtime NPZ package.
- Produces: one JSON result containing four stage metrics, per-path hashes, determinism, and environment.

- [ ] Write failing tests for command construction, offline environment, CPU rejection, stage order, OOM-only batch reduction, and JSON validation.
- [ ] Implement the parent boundary and standalone runner.
- [ ] Make tests pass and commit.

### Task 5: Atomic reports and CLI

**Files:**
- Create: `backend/quantradar/kronos/runtime/report.py`
- Create: `backend/quantradar/kronos/runtime/orchestrator.py`
- Create: `scripts/kronos_gpu_smoke.py`
- Modify: `Makefile`
- Modify: `pyproject.toml`
- Test: `tests/unit/kronos/test_runtime_orchestrator.py`
- Test: `tests/unit/kronos/test_runtime_cli.py`

**Interfaces:**
- Produces: `make kronos-gpu-smoke`, atomic reports, and an honest completion marker.

- [ ] Write failing tests for atomic publication, manifest hashes, subprocess failure, and the pass marker.
- [ ] Implement orchestration, reporting, CLI, Make target, and pytest markers.
- [ ] Make tests pass and commit.

### Task 6: Real environment and GPU acceptance

**Files:**
- Generate: `.venv-kronos/` (ignored)
- Generate: `models/kronos/kronos_model_lock.json`
- Generate: `reports/kronos/runtime_smoke/*`
- Modify: `docs/ACTIVE_PHASE.md`
- Modify: `docs/CURRENT_STATE.md`

**Interfaces:**
- Consumes: Tasks 1-5.
- Produces: real machine evidence and `KRONOS_BASE_GPU_RUNTIME_PASS` or an explicit BLOCKED result.

- [ ] Run setup and verify every local source/model file hash.
- [ ] Run the real GPU smoke stages in the required order.
- [ ] Re-run the fixed-seed probe and validate exact hashes.
- [ ] Validate the report manifest and confirm Goal 0 gates did not change.
- [ ] Update status docs with measured facts and commit.
- [ ] Run Goal 0/1 tests, compile checks, diff checks, and the proportional project regression suite.
