# Current State

`docs/ACTIVE_PHASE.md` is the sole source of truth for the current goal. This
file records present facts, not plans or chronological logs.

## Repository

- Branch: `feat/report-research-mvp`
- Remote backup: `origin/feat/report-research-mvp`
- HEAD: the current commit on this branch (`git rev-parse HEAD`).
- Local runtime state under `data/runtime/` is ignored and is not source data.

## Active Product Work

`REPORT_MVP_ENGINEERING_PASS`, `REPORT_MVP_WEB_VISIBILITY_PASS`, and
`REPORT_MVP_YESTERDAY_DIGEST_PASS` are complete and merged to `main` through
PR #3 (merge commit `7ba6cff`). The only active goal is
`REPORT_MVP_7D_LIVE_PASS`; its seven real operating-day observation is active.
`REPORT_MVP_BASELINE_PASS`, `REPORT_MVP_AGNES_PASS`,
`REPORT_MVP_PIPELINE_RESUME_PASS`, `REPORT_MVP_DELIVERY_PASS`, and
`REPORT_MVP_OPERATIONS_PASS` are historical completed Goals.

### Enterprise Alert Research MVP: implemented

- Isolated SQLAlchemy registry for reports, snapshots, artifacts, stage runs,
  analyses, digests, and outbox rows.
- QYJ collection using the user-authorized persistent browser profile; 364
  real snapshots were collected across 2026-08-26 through 2026-08-28.
- QYJ intake applies `depthOnly=1` exclusively to HOT, preserves the
  unfiltered STRATEGY and FINANCIAL_ENGINEERING channels, and each scheduled
  run backfills yesterday plus the two preceding publication dates before it
  delivers yesterday's Digest. `icon=wx` records use their authenticated QYJ
  detail link to obtain canonical Markdown; a login page becomes a failed,
  recoverable PREPARE stage rather than a false success.
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
- A versioned Snapshot-scoped 2026-08-29 Digest is persisted with header
  `QuantRadar 昨日研报摘要 · 2026-08-29`. It independently synthesizes HOT,
  STRATEGY, and FINANCIAL_ENGINEERING from `ResearchReportSnapshot` members:
  43 / 7 / 2 collected, with 43 / 7 / 2 successful analyses and no processing
  exceptions. It does not use
  `FIXED_INCOME` and it has no silent membership omissions.
- The new canonical multi-source analysis profile
  `42f9bd54f5ed247977d02ef2fb1382e30634cecee1bff6a277cfcb64797f1e59` has
  48 successful analyses, zero pending/retryable/terminal analysis failures,
  and an idempotent Digest replay that made zero Agnes requests.
- Canonical source accounting for the 2026-08-29 snapshots is 48 distinct
  persisted reports and 48 `PARSE_OK` canonical Markdown artifacts. The six
  records formerly classified as unsupported have real `abstract` embedded
  HTML and now correctly use that source after their empty PDF attachment was
  ignored. Components are audited as 33 PDF primary, 19 duplicate HTML
  excluded, 14 supplementary HTML included, and 15 HTML-only included. The
  corresponding acceptance manifest is
  `/data/ken/.cache/quantradar/research/acceptance/yesterday-digest-2026-08-29.json`.
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

### Merge-gate facts

- `MULTIFORMAT_CONTENT_GATE` is `PASS`: all actual 2026-08-29 PDF and
  embedded-HTML sources completed QYJ metadata → canonical Markdown → quality
  gate → Agnes → Evidence. The 535 persisted historical QYJ metadata records
  contain no `mp.weixin.qq.com` source. Therefore
  `WEIXIN_ADAPTER_IMPLEMENTED=true`, `WEIXIN_QYJ_SAMPLE_OBSERVED=false`,
  `WEIXIN_PUBLIC_SMOKE_PASS=true`, and
  `WEIXIN_QYJ_LIVE_VERIFIED=PENDING_FIRST_REAL_SAMPLE`. `url-md 0.2.0` is
  installed at `/home/ken/.url-md/bin/url-md` (SHA-256
  `d1227011102c71ba38a8083b6dbb9a9c2670da88019162b6b25ef6a4e5d42616`); its
  public-Weixin smoke passed, while it is not represented as QYJ live proof.
- `REPORT_MVP_7D_LIVE_PASS` remains false at `0 / 7`. Historical replay does
  not advance the count. The formal user-level systemd timer is enabled for
  the observation.

## Frozen Historical Facts

- BulletTrade WebUI/backtest is sealed with native report artifacts,
  reproducible snapshots, async worker recovery, and CI coverage.
- Qlib research hardening and OOS tooling are complete historical work.
- Kronos Goals 0–2 have recorded data-audit, GPU-runtime, and pipeline
  evidence. Their data/real-assist limitations remain recorded.

## Verification

- Full backend suite: the prior `make test` result was `327 passed, 1 failed`;
  the sole failure was a frozen live Kronos MySQL audit timeout. The exact test
  subsequently passed both on `origin/main` and on this branch, so it is a
  transient external failure, `research_related=false`, and
  `research_new_regression=false`.
- Research unit suite: `91 passed, 0 failed`.
- Frontend `npm run typecheck`: passed.
- Frontend `npm run build`: passed; the known 2.19 MB bundle warning remains
  frozen and out of scope.
- `git diff --check`: passed.
