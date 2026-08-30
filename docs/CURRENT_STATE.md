# Current State

`docs/ACTIVE_PHASE.md` is the sole source of truth for the current goal. This
file records present facts, not plans or chronological logs.

## Repository

- Branch: `feat/report-research-mvp`
- Remote backup: `origin/feat/report-research-mvp`
- HEAD: the current commit on this branch (`git rev-parse HEAD`).
- Local runtime state under `data/runtime/` is ignored and is not source data.

## Active Product Work

`REPORT_MVP_ENGINEERING_PASS` and `REPORT_MVP_WEB_VISIBILITY_PASS` are
complete. The current active goal is `REPORT_MVP_7D_LIVE_PASS` observation;
Research code is frozen. Passed engineering goals:
`REPORT_MVP_BASELINE_PASS`, `REPORT_MVP_AGNES_PASS`,
`REPORT_MVP_PIPELINE_RESUME_PASS`, `REPORT_MVP_DELIVERY_PASS`, and
`REPORT_MVP_OPERATIONS_PASS`. `REPORT_MVP_ENGINEERING_PASS` is complete.

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
  `research pipeline`, `make research-prepare`, `make research-analyze`, and
  `make research-pipeline`.
- Resumable QYJ → MinerU → Agnes pipeline with durable PREPARE/ANALYZE stage
  checkpoints and per-report failure isolation. Live resume evidence:
  `/data/ken/.cache/quantradar/research/analysis/acceptance/pipeline-resume-2026-08-28.json`;
  the first run recorded two successful stages of each type, and the rerun
  collected 99 metadata records while skipping both completed heavy stages.
- Daily Digest, unique notification-key Outbox, and real Feishu delivery.
  `/data/ken/.cache/quantradar/research/analysis/acceptance/delivery-2026-08-28.json`
  records a successful first send and an idempotent second run that did not
  send again.
- Single-instance runtime lock, credential-redacted JSON operation records,
  and verified but not enabled `systemd --user` service/timer templates.
  A real locked 2026-08-28 pipeline rerun collected 99 records, skipped
  completed PREPARE/ANALYZE stages, and wrote a safe runtime log.
- Structured live acceptance evidence:
  `/data/ken/.cache/quantradar/research/analysis/acceptance/agnes-acceptance-2026-08-29.json`.
  It verifies 30 successful real reports across three dates, report/Markdown/
  chunk Evidence traceability, one-chunk and 13-chunk paths, recovered retry,
  and an idempotent replay that made no Agnes request.
- Read-only dates/reports/status APIs and minimal Research verification UI.
- Read-only visibility APIs for overview, report detail, registered PDF and
  Markdown artifacts, Daily Digest, operations, and observation state. Artifact
  delivery is constrained to the Research data root and database-registered
  report identities; no local path is accepted from a caller.
- Existing `ResearchMVP.tsx` now has 今日概览、研报列表、Daily Digest、运行状态
  tabs. It renders backend-computed counters, structured Agnes/Evidence/Audit
  details, formatted Markdown, stage summaries, and no Research write actions.

### Enterprise Alert Research MVP: not implemented

- `REPORT_MVP_7D_LIVE_PASS` is active but remains false at `0 / 7` real
  operating days. Historical replay does not advance the count.

## Frozen Historical Facts

- BulletTrade WebUI/backtest is sealed with native report artifacts,
  reproducible snapshots, async worker recovery, and CI coverage.
- Qlib research hardening and OOS tooling are complete historical work.
- Kronos Goals 0–2 have recorded data-audit, GPU-runtime, and pipeline
  evidence. Their data/real-assist limitations remain recorded.

## Verification

- CI-equivalent backend: `165 passed, 143 skipped, 0 failed` (`make test`).
- Research unit suite: `69 passed, 0 failed`.
- Frontend `npm run typecheck`: passed.
- Frontend `npm run build`: passed; the known 2.16 MB bundle warning remains
  frozen and out of scope.
- `git diff --check`: passed for the Web visibility change before its commit.

## Current Next Action

Observe seven real operating days. Do not claim `REPORT_MVP_7D_LIVE_PASS`
before the seventh recorded operating day.
