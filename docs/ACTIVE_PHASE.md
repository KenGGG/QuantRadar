# QuantRadar Active Phase

**Milestone:** `REPORT_MVP_7D_LIVE_PASS`
**Active Goal:** `REPORT_MVP_7D_LIVE_PASS`
**Status:** ACTIVE

`MULTIFORMAT_CONTENT_GATE = PASS`

`REPORT_MVP_YESTERDAY_DIGEST_PASS = PASS`

`REPORT_MVP_7D_LIVE_PASS = false`

## Scope

The only active work is observing seven real operating days of the merged
Enterprise Alert Research MVP.

```text
QYJ metadata → content-source detection → canonical Markdown + quality → Agnes analysis
→ resumable pipeline → Daily Digest → Feishu Outbox → delivery → operations
```

## Merge Gate

`MULTIFORMAT_CONTENT_GATE` is mandatory and is `PASS`. It requires
an audited, source-accounted canonical Markdown path for every accessible
QYJ report body (PDF, Weixin, embedded HTML, and public/authenticated HTML)
in the three formal channels. The real 2026-08-29 inventory is the acceptance
baseline; unsupported or inaccessible sources must be explicit failures, never
silently omitted. The acceptance corpus observed PDF and embedded HTML live
end-to-end. `WEIXIN_ADAPTER_IMPLEMENTED=true`,
`WEIXIN_QYJ_SAMPLE_OBSERVED=false`,
`WEIXIN_PUBLIC_SMOKE_PASS=true`, and
`WEIXIN_QYJ_LIVE_VERIFIED=PENDING_FIRST_REAL_SAMPLE`; the first real QYJ
Weixin URL is guarded through the normal canonical Markdown pipeline.

## Frozen

- Kronos Goals 0–2 and Kronos WebUI
- BulletTrade and its WebUI/backtest paths
- Qlib research
- frontend bundle optimization
- ETF, live trading, new models, and unrelated product work

The corrected Digest was merged through PR #3. The formal user-level systemd
timer is enabled for this observation; historic replay does not advance the
seven-day count.

The only formal Research channels are:

- `HOT` — 热门研报 — `hotReport=1`, `secondReportType=`.
- `STRATEGY` — 策略研究 — `secondReportType=10301,10302,10303`.
- `FINANCIAL_ENGINEERING` — 金融工程 — `secondReportType=10202,10203`.

Do not add or substitute `FIXED_INCOME`; preserve existing channel parameters.

## Completed Goals

- `REPORT_MVP_BASELINE_PASS` — `PASS`
- `REPORT_MVP_AGNES_PASS` — `PASS`
- `REPORT_MVP_PIPELINE_RESUME_PASS` — `PASS`
- `REPORT_MVP_DELIVERY_PASS` — `PASS`
- `REPORT_MVP_OPERATIONS_PASS` — `PASS`
- `REPORT_MVP_WEB_VISIBILITY_PASS` — `PASS`
- `MULTIFORMAT_CONTENT_GATE` — `PASS`
- `REPORT_MVP_YESTERDAY_DIGEST_PASS` — `PASS`

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

None. Do not begin unrelated development during the observation.

## Observation Goal

`REPORT_MVP_7D_LIVE_PASS = false`. It requires seven real operating days after
the corrected Digest was merged. Historical replay never advances the count.

## Completion Rule

`REPORT_MVP_7D_LIVE_PASS = false` until seven real operating days are recorded.
