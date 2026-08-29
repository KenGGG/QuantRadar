# QuantRadar Active Phase

**Milestone:** `REPORT_MVP_ENGINEERING_PASS`
**Active Goal:** `REPORT_MVP_DELIVERY_PASS`
**Status:** ACTIVE

## Scope

The only active work is the Enterprise Alert research-report MVP.

```text
QYJ metadata → PDF + quality → MinerU Markdown → Agnes analysis
→ resumable pipeline → Daily Digest → Feishu Outbox → delivery → operations
```

## Frozen

- Kronos Goals 0–2 and Kronos WebUI
- BulletTrade and its WebUI/backtest paths
- Qlib research
- frontend bundle optimization
- ETF, live trading, new models, and unrelated product work

Completed historical work remains valid evidence; it is not an active goal.

## Completed Goals

- `REPORT_MVP_BASELINE_PASS` — `PASS`
- `REPORT_MVP_AGNES_PASS` — `PASS`
- `REPORT_MVP_PIPELINE_RESUME_PASS` — `PASS`

Agnes acceptance includes live QYJ reports across 2026-08-26, 2026-08-27,
and 2026-08-28; short and chunked-long analysis, traceable Evidence,
recoverable retry, and idempotent replay were verified and saved as structured
runtime evidence.

## Current Goal: REPORT_MVP_DELIVERY_PASS

Implement and verify the Daily Digest, idempotent Outbox, and Feishu delivery
path. It must not enter systemd or frozen work.

## Queued Goals

1. `REPORT_MVP_OPERATIONS_PASS`

## Observation Goal

`REPORT_MVP_7D_LIVE_PASS = false`. It requires seven real operating days and
cannot be claimed during engineering acceptance.

## Completion Rule

After the active goal passes, update this file, commit the transition, and
continue immediately to the next queued goal. `REPORT_MVP_ENGINEERING_PASS`
requires all queued engineering goals; it does not imply the 7-day live pass.
