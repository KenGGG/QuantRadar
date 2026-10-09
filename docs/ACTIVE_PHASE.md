# QuantRadar2 Active Phase

Updated: 2026-10-09 (Asia/Shanghai).

**Milestone:** QUANTRADAR2_RESEARCH_WORKBENCH_V1
**Active Goal:** G2_MINUTE_RECOVERY_AND_FROZEN_REPLAY_ACCEPTANCE
**Status:** IN_PROGRESS

## Authoritative plan

[QuantRadar2 development plan](QUANTRADAR2_DEVELOPMENT_PLAN.md) is the authorized implementation plan. Execute G0 → G1 → G2 continuously; stop at first-release delivery. G3 is future work, not an active goal.

## Current task

G0 and G1 passed with documented data limitations. See docs/acceptance/quantradar2-g0/README.md and docs/acceptance/quantradar2-g1/README.md. Implement finite frozen input capture/replay and validate the daily/minute strategy suite, task cancellation/timeout/restart, final parity and Windows delivery.

## Confirmed user decisions

SQLite is authorized for application metadata. QuantRadar2 does not develop trading capabilities. QMT-managed market-data cache writes are allowed. Do not restore dual Dolt/DataHub or add data sources; do not modify BulletTrade backtest engine or push old main.

## Progress

- G0 baseline, relevant source audit, Windows frontend build and independent Python environment passed.
- Dedicated data service 127.0.0.1:58621 has features=data, broker actions unavailable; offline rejection test passed with zero Gateway calls. Existing Gateway remains trading-enabled.
- Independent .venv-v2 imports audited external BulletTrade 0.10.0; pip check passed; requirements-v2.lock recorded.
- Old V1 state archived; development branch codex/quantradar2-workbench, no pushes.
- G1 accepted: SQLite, FIFO subprocess runner, native reports, V2 API and three-page WebUI. 10 targeted tests and native daily/API/browser acceptance passed.

## Sequential queue

1. G0_BASELINE_AND_DATA_ONLY_BOUNDARY
2. G1_SQLITE_API_RUNNER_AND_WORKBENCH
3. G2_MINUTE_RECOVERY_AND_FROZEN_REPLAY_ACCEPTANCE

A gate passes only with its required evidence. Record non-core data limitations without claiming they are fixed. Old V1 DataHub phase labels do not apply to V2.
