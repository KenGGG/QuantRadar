# QuantRadar Active Phase

**Milestone:** `REPORT_MVP_ENGINEERING_PASS`
**Active Goal:** `REPORT_MVP_AGNES_PASS`
**Status:** ACTIVE

## Scope

The only active work is the Enterprise Alert research-report MVP.

```text
QYJ metadata → PDF + quality → MinerU Markdown → Agnes analysis
→ Daily Digest → Feishu Outbox → delivery → resumable operations
```

## Frozen

- Kronos Goals 0–2 and Kronos WebUI
- BulletTrade and its WebUI/backtest paths
- Qlib research
- frontend bundle optimization
- ETF, live trading, new models, and unrelated product work

Completed historical work remains valid evidence; it is not an active goal.

## Completed Goal: REPORT_MVP_BASELINE_PASS

`PASS` — the 12 pre-existing Research MVP commits are protected on
`origin/feat/report-research-mvp`; the active-goal documents, runtime ignore
rules, permanent agent protocol, and versioned plan are all in place.

## Current Goal: REPORT_MVP_AGNES_PASS

Implement versioned, idempotent Agnes full-text analysis for MinerU Markdown.
The result must be traceable to its report, PDF, Markdown, model, and prompt.

## Queued Goals

1. `REPORT_MVP_AGNES_PASS`
2. `REPORT_MVP_PIPELINE_RESUME_PASS`
3. `REPORT_MVP_DELIVERY_PASS`
4. `REPORT_MVP_OPERATIONS_PASS`

## Observation Goal

`REPORT_MVP_7D_LIVE_PASS = false`. It requires seven real operating days and
cannot be claimed during engineering acceptance.

## Completion Rule

After the active goal passes, update this file, commit the transition, and
continue immediately to the next queued goal. `REPORT_MVP_ENGINEERING_PASS`
requires all queued engineering goals; it does not imply the 7-day live pass.
