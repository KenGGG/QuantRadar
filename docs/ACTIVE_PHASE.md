# QuantRadar Active Phase

**Milestone:** `REPORT_MVP_7D_LIVE_PASS`
**Active Goal:** `REPORT_MVP_7D_LIVE_PASS`
**Status:** OBSERVATION

## Scope

The only active work is the real seven-operating-day observation of the frozen
Enterprise Alert research-report MVP.

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

All Research code is frozen. The existing WebUI is read-only and may only read
persisted ResearchStore records and registered artifacts; it must not change
collection, parsing, Agnes, Digest, Outbox, Feishu, or systemd behavior.

## Completed Goals

- `REPORT_MVP_BASELINE_PASS` — `PASS`
- `REPORT_MVP_AGNES_PASS` — `PASS`
- `REPORT_MVP_PIPELINE_RESUME_PASS` — `PASS`
- `REPORT_MVP_DELIVERY_PASS` — `PASS`
- `REPORT_MVP_OPERATIONS_PASS` — `PASS`
- `REPORT_MVP_WEB_VISIBILITY_PASS` — `PASS`

Agnes acceptance includes live QYJ reports across 2026-08-26, 2026-08-27,
and 2026-08-28; short and chunked-long analysis, traceable Evidence,
recoverable retry, and idempotent replay were verified and saved as structured
runtime evidence.

## Operations Acceptance

Single-instance locking, redacted structured runtime records, and unenabled
`systemd --user` service/timer units are implemented and verified. The real
2026-08-28 pipeline rerun collected 99 metadata records while safely skipping
completed stages and writing an operational record.

## Queued Goals

None. Research engineering is frozen during observation.

## Observation Goal

`REPORT_MVP_7D_LIVE_PASS = false`. It requires seven real operating days and
cannot be claimed during engineering acceptance.

## Completion Rule

`REPORT_MVP_7D_LIVE_PASS = false` until seven real operating days are recorded.
Historic replay never advances it. Do not begin unrelated development while
the observation is active.
