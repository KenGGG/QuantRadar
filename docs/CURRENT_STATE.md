# Current State

`docs/ACTIVE_PHASE.md` is the sole source of truth for the current goal. This
file records present facts, not plans or chronological logs.

## Repository

- Branch: `feat/report-research-mvp`
- Remote backup: `origin/feat/report-research-mvp`
- HEAD at the Agnes acceptance transition: `964dab0`
  (`chore(research): add report MVP make targets`).
- Local runtime state under `data/runtime/` is ignored and is not source data.

## Active Product Work

Milestone: `REPORT_MVP_ENGINEERING_PASS`. Passed goals:
`REPORT_MVP_BASELINE_PASS`, `REPORT_MVP_AGNES_PASS`. Sole active goal:
`REPORT_MVP_PIPELINE_RESUME_PASS`.

### Enterprise Alert Research MVP: implemented

- Isolated SQLAlchemy registry for reports, snapshots, artifacts, stage runs,
  analyses, digests, and outbox rows.
- QYJ collection using the user-authorized persistent browser profile; 364
  real snapshots were collected across 2026-08-26 through 2026-08-28.
- Atomic PDF artifacts, shared MinerU Markdown publication, parse-quality
  checks, and 57 real Markdown reports across those three dates.
- Versioned Agnes HTTP adapter with configured 19 RPM request spacing,
  short-report and chunked-long-report analysis, synthesis, non-empty scoped
  Evidence validation, durable retryable failure state, and current-contract
  validation before idempotent reuse.
- Formal operator entry points: `research prepare`, `research analyze`,
  `make research-prepare`, and `make research-analyze`.
- Structured live acceptance evidence:
  `/data/ken/.cache/quantradar/research/analysis/acceptance/agnes-acceptance-2026-08-29.json`.
  It verifies 30 successful real reports across three dates, report/Markdown/
  chunk Evidence traceability, one-chunk and 13-chunk paths, recovered retry,
  and an idempotent replay that made no Agnes request.
- Read-only dates/reports/status APIs and minimal Research verification UI.

### Enterprise Alert Research MVP: not implemented

- A single resumable collect-to-analysis pipeline and resume command.
- Daily Digest, idempotent Feishu outbox sender, and delivery verification.
- Single-instance lock, structured logs, `systemd --user` units, and final
  engineering acceptance.
- Real Feishu delivery and the separate seven-day observation are not started.

## Frozen Historical Facts

- BulletTrade WebUI/backtest is sealed with native report artifacts,
  reproducible snapshots, async worker recovery, and CI coverage.
- Qlib research hardening and OOS tooling are complete historical work.
- Kronos Goals 0–2 have recorded data-audit, GPU-runtime, and pipeline
  evidence. Their data/real-assist limitations remain recorded.

## Verification

- CI-equivalent backend: `156 passed, 143 skipped, 0 failed` (`make test`).
- Research unit suite: `60 passed, 0 failed`.
- Frontend `npm run typecheck`: passed.
- Frontend `npm run build`: passed; the known 2.16 MB bundle warning remains
  frozen and out of scope.
- `git diff --check`: pending final state-transition commit verification.

## Current Next Action

Complete `REPORT_MVP_PIPELINE_RESUME_PASS`.
