# Current State

`docs/ACTIVE_PHASE.md` is the sole source of truth for the current goal. This
file records present facts, not a delivery plan or chronological log.

## Repository

- Branch: `feat/report-research-mvp`
- The branch contains 12 local Research MVP commits ahead of `origin/main`.
- Remote backup: `origin/feat/report-research-mvp`.
- Baseline establishment: `8732f91` (`chore(research): establish report MVP active baseline`).
- Local runtime state under `data/runtime/` is ignored and is not source data.

## Active Product Work

Milestone: `REPORT_MVP_ENGINEERING_PASS`. `REPORT_MVP_BASELINE_PASS` is
passed. Sole active goal: `REPORT_MVP_AGNES_PASS`.

### Enterprise Alert Research MVP: implemented

- Isolated SQLAlchemy registry for reports, snapshots, artifacts, stage runs,
  analyses, digests, and outbox rows.
- Environment-based Research settings and local artifact directory layout.
- QYJ metadata collection with stable identities, channel ordering, pagination,
  and diagnostic authentication failure handling.
- Atomic PDF artifacts with SHA-256 identity and page-count checks.
- Shared MinerU loopback adapter, safe output handling, Markdown publication,
  and parse-quality checks.
- Read-only dates/reports/status APIs, minimal Research verification UI, and
  operator `health` / `collect` commands.

### Enterprise Alert Research MVP: not implemented

- Agnes full-text analysis with versioned/idempotent persistence.
- A single resumable collect-to-digest pipeline and resume command.
- Daily Digest, idempotent Feishu outbox sender, and delivery verification.
- Single-instance lock, structured logs, `systemd --user` units, and final
  engineering acceptance.
- Live evidence: 30 reports over three dates, real Feishu delivery, and the
  separate seven-day observation.

## Frozen Historical Facts

- BulletTrade WebUI/backtest is sealed with native report artifacts,
  reproducible snapshots, async worker recovery, and CI coverage.
- Qlib research hardening and OOS tooling are complete historical work.
- Kronos Goals 0–2 have recorded data-audit, GPU-runtime, and pipeline
  evidence. Their data/real-assist limitations remain recorded.

## Verification at Baseline Start

- CI-equivalent backend: `115 passed, 143 skipped, 0 failed`
  (`QUANTRADAR_FORCE_NO_DOLT=1 make test`).
- Research unit suite: `19 passed, 0 failed`.
- Frontend `npm run build` (including TypeScript checking): passed.
- The 2.16 MB frontend bundle warning is known and out of scope.

## Current Next Action

Complete `REPORT_MVP_AGNES_PASS`.
