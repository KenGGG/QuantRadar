# Kronos 门禁正确性 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 PR #2 的 PIT 股票池、回测门禁、审计缓存可复现性和 CI Dolt 隔离问题。

**Architecture:** `universe_spec` 定义全 A 股信号日与候选资格，`signal.inputs` 和 runtime 输入构建均使用共享的市场 90 日窗口校验。审计产物和研究流水线以同一 Dolt commit 绑定；能力门禁把研究、部分真实和正式回测分开表达。

**Tech Stack:** Python 3.12、pytest、pandas、NumPy、Dolt、GitHub Actions。

**Spec:** `docs/superpowers/specs/2026-08-23-kronos-gate-correctness-design.md`

## Global Constraints

- 默认 universe 必须保持 `all_a_liquid`，不得恢复 CSI300 PIT 全局阻塞。
- 所有生产改动先有一个观察到预期失败的回归测试。
- 所有真实 Dolt 测试带 `requires_dolt`，CI 无 Dolt 时必须跳过。
- 审计缓存不匹配或不可读时必须保守降级，不能默认 ready。

---

### Task 1: 严格全 A 股 PIT 候选与市场窗口

**Files:**
- Modify: `backend/quantradar/kronos/universe_spec.py`
- Modify: `backend/quantradar/kronos/signal/inputs.py`
- Modify: `backend/quantradar/kronos/runtime/inputs.py`
- Modify: `tests/unit/kronos/test_signal_inputs.py`
- Modify: `tests/unit/kronos/test_universe_all_a_liquid.py`
- Modify: `tests/unit/kronos/test_runtime_inputs.py`

**Interfaces:**
- Produces: `all_a_liquid_symbols(connection, as_of)` only returns symbols with a price at `as_of`.
- Produces: shared canonical market-date sequence consumed by `validate_window`.
- Produces: `list_signal_dates(..., ALL_A_LIQUID)` limited to `latest_price_date`.

- [ ] **Step 1: Write failing candidate and date-limit tests**

```python
assert all_a_liquid_symbols(connection, dt.date(2026, 8, 18)) == ["SH600001"]
assert list_signal_dates(provider, start="2026-08-17", end="2026-08-31") == [dt.date(2026, 8, 18)]
```

- [ ] **Step 2: Run the two tests and verify they fail because historical symbols and future calendar days are accepted.**

Run: `PYTHONPATH=backend .venv/bin/python -m pytest tests/unit/kronos/test_signal_inputs.py tests/unit/kronos/test_universe_all_a_liquid.py -q`

- [ ] **Step 3: Implement signal-date price query and latest-price clamp**

```python
effective_end = min(_date(end), latest_price_date(provider.connection))
"WHERE tradedate = %s AND symbol REGEXP %s"
```

- [ ] **Step 4: Write failing missing-window-date and direct-future-signal-date tests**

```python
assert selection.exclusions["000001.XSHE"] == "price dates do not match the latest 90 market days"
with pytest.raises(RuntimeError, match="latest available price date"):
    collect_week_input_package(..., signal_date="2026-08-31")
```

- [ ] **Step 5: Implement canonical 90-market-day date equality check in both input paths**

```python
expected_dates = tuple(open_days[-LOOKBACK_DAYS:])
if window.dates != expected_dates:
    return "price dates do not match the latest 90 market days"
```

- [ ] **Step 6: Run focused PIT tests and commit**

Run: `PYTHONPATH=backend .venv/bin/python -m pytest tests/unit/kronos/test_signal_inputs.py tests/unit/kronos/test_universe_all_a_liquid.py tests/unit/kronos/test_runtime_inputs.py -q`

### Task 2: 分离研究、真实与正式回测门禁

**Files:**
- Modify: `backend/quantradar/kronos/data_audit/gates.py`
- Modify: `backend/quantradar/kronos/pipeline.py`
- Modify: `scripts/kronos_data_audit.py`
- Modify: `scripts/kronos_research_pipeline.py`
- Modify: `tests/unit/kronos/test_data_audit_core.py`
- Modify: `tests/unit/kronos/test_data_audit_runner.py`
- Modify: `tests/unit/kronos/test_pipeline.py`

**Interfaces:**
- Produces: boolean `research_backtest_ready`.
- Produces: `formal_backtest_ready=False` for partial tradeability or unavailable corporate actions.

- [ ] **Step 1: Write failing gate assertions for partial tradeability/corporate-action evidence**

```python
assert result["research_backtest_ready"] is True
assert result["realistic_backtest_ready"] is True
assert result["formal_backtest_ready"] is False
```

- [ ] **Step 2: Run gate tests and verify they fail because formal is currently an alias of realistic.**

Run: `PYTHONPATH=backend .venv/bin/python -m pytest tests/unit/kronos/test_data_audit_core.py tests/unit/kronos/test_data_audit_runner.py -q`

- [ ] **Step 3: Implement the independent formal predicate and propagate new field**

```python
research_backtest_ready = kronos_signal_research_ready
formal_backtest_ready = research_backtest_ready and tradeability_status is AuditStatus.PASS and action_ready
```

- [ ] **Step 4: Update pipeline/script outputs and run focused gate tests**

Run: `PYTHONPATH=backend .venv/bin/python -m pytest tests/unit/kronos/test_data_audit_core.py tests/unit/kronos/test_data_audit_runner.py tests/unit/kronos/test_pipeline.py tests/unit/kronos/test_pipeline_cli.py tests/unit/kronos/test_data_audit_cli.py -q`

- [ ] **Step 5: Commit**

### Task 3: 以 Dolt commit 绑定审计缓存

**Files:**
- Modify: `backend/quantradar/kronos/data_audit/runner.py`
- Modify: `backend/quantradar/kronos/data_audit/report.py`
- Modify: `backend/quantradar/kronos/pipeline.py`
- Modify: `tests/unit/kronos/test_data_audit_runner.py`
- Modify: `tests/unit/kronos/test_pipeline.py`

**Interfaces:**
- Produces: `data_gate.json["data_commit"] == audit_manifest["run_end_commit"]`.
- Produces: research manifest `audit_gate_data_commit` and `audit_gate_matches_data_commit`.

- [ ] **Step 1: Write failing tests for audit gate commit and stale/missing cache downgrade**

```python
assert gates["data_commit"] == "abc123"
assert result["gate"]["realistic_backtest_ready"] is False
assert manifest["audit_gate_matches_data_commit"] is False
```

- [ ] **Step 2: Run tests and verify the missing-cache test fails because it currently defaults realistic ready to true.**

Run: `PYTHONPATH=backend .venv/bin/python -m pytest tests/unit/kronos/test_data_audit_runner.py tests/unit/kronos/test_pipeline.py -q`

- [ ] **Step 3: Attach the immutable audit commit before report publication and validate cache when consumed**

```python
gates = {**derive_data_gates(evidence), "data_commit": start_commit}
cache_matches = cached_gate and cached_gate.get("data_commit") == data_commit
realistic_backtest_ready = bool(cached_gate.get("realistic_backtest_ready")) if cache_matches else False
```

- [ ] **Step 4: Run audit/pipeline focused suite and commit**

Run: `PYTHONPATH=backend .venv/bin/python -m pytest tests/unit/kronos/test_data_audit_runner.py tests/unit/kronos/test_pipeline.py tests/unit/kronos/test_pipeline_cli.py -q`

### Task 4: CI-safe live-test marking and final verification

**Files:**
- Modify: `tests/unit/kronos/test_universe_all_a_liquid.py`
- Modify: any newly identified live Dolt test missing `pytest.mark.requires_dolt`
- Test: `tests/unit/kronos/test_universe_all_a_liquid.py`

- [ ] **Step 1: Write a CI-mode test/run that proves the live module skips with `QUANTRADAR_FORCE_NO_DOLT=1`.**

Run: `QUANTRADAR_FORCE_NO_DOLT=1 PYTHONPATH=backend .venv/bin/python -m pytest tests/unit/kronos/test_universe_all_a_liquid.py -q`

- [ ] **Step 2: Add `requires_dolt` only to tests that construct/query real investment data; retain fake-provider unit tests unmarked.**

- [ ] **Step 3: Verify focused tests, full backend suite, and frontend build**

Run: `PYTHONPATH=backend .venv/bin/python -m pytest tests/unit/kronos -q`

Run: `make test`

Run: `cd frontend && npm run build`

- [ ] **Step 4: Inspect diff and test output, then commit all remaining changes.**
