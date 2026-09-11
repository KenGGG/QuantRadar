# Current State

`docs/ACTIVE_PHASE.md` is the sole source of truth for the current goal. This file records current facts.

## Repository and runtime

- Development branch: `main`. DataHub feature work and the launcher change are merged into main.
- The Web process at `127.0.0.1:7231` serves the main checkout.
- Old worktrees remain available for reference. Local runtime and browser scratch files are not source data.
- Active DataHub goal: `DATAHUB_V2_HISTORICAL_REUSE_AND_INCREMENTAL_REPAIR`; V1 remediation remains a completed prerequisite.
- Current verification and source limitations: [2026-09-11 remediation evidence](acceptance/datahub-remediation-2026-09-11/README.md).

## DataHub facts

- Base Dolt: `/data/investment_data`, read-only SQL on localhost:3307. Approved upstream is `chenditc/investment_data`; only clean fast-forward synchronization is allowed.
- Supplemental Dolt: `/data/quantradar_data`, localhost:3308. Candidate branches and immutable paired manifests isolate publication from backtests.
- The failure baseline contains 5,554 securities: 5,235 COMPLETE, 196 FAILED, 123 legacy NOT_COVERED. The 196 failures share the AKShare 1.18.94 NoneType parse fingerprint. The 123 records lack sufficient coverage evidence and remain unverified.
- Current release is `R22a53f013266373d`, pairing the fixed base commit with supplemental commit `ift7hg4vnjei2eqaqisg61s461nnodig`: 5,235 valuation securities / 9,206,992 rows through 2026-09-11. The valuation failure baseline remains 196 parsing failures plus 123 unverified-coverage records; no failed security was silently reclassified or deleted.
- The current release has 11,347 published BaoStock trade-status records for 298 securities from 2023-06-30 through 2026-07-31. They fill verified base gaps only and remain PIT_PARTIAL. 600837.SH and 601989.SH remain `NOT_COVERED` because their fixed-base price history ends before each requested status date; no state was invented. The strict low-Beta strategy successfully completed its 2023-07-03 first-rebalance window against R22. Evidence: `acceptance/datahub-v2-p3/low-beta-status-full-repair.md`.
- Low-Beta status repair journals are keyed by the fixed base commit and exact date×security scope, separately from the release-specific audit fingerprint. The R22 scope journal reused the completed R3 evidence (298 COMPLETE, 2 NOT_COVERED), so a later release pointer does not trigger a duplicate BaoStock download.
- Canonical valuation fields are PE_TTM, PB_MRQ, PS_TTM and PCF_OCF_TTM. BaoStock NCF semantics are frozen and cannot substitute for OCF.
- PIT is PARTIAL. Cross-source values, historical availability and full lifecycle/field coverage are not comprehensively verified.
- Current page has three blocks: published usable coverage, current update stages, and grouped issues. Published coverage separates `/data/investment_data` from `/data/quantradar_data`, including the BaoStock state supplement; download counts and published coverage are displayed separately.
- CLI/UI/timer share the daily coordinator. A same-target watermark prevents repeated transport checks; Eastmoney's stock API still returns each requested stock's full history.
- Research reads pin both commits. Supported valuation queries require an explicit stock universe; missing required records/fields and explicitly requested strict PIT cause errors.
- Trusted base synchronization fast-forwarded the base commit and restored the read-only SQL service. Current price coverage is 5,556 securities through 2026-09-11; ST/paused coverage remains 5,183 securities through 2023-06-09 and is displayed separately.
- The strict low-Beta status tail is precisely known: 38 monthly dependency dates from 2023-06-30 through 2026-07-31, 11,400 date×constituent keys across 300 stocks.  The base CSI 300 constituent snapshot used for these dates remains 2022-07-01, so post-2022 constituent-history completeness is not established.
- New releases normalize price volume from lots to shares and amount from thousand yuan to yuan. Historical releases retain their original unit contract for replay.
- Latest published release and live publication outcome are recorded in the linked acceptance evidence.

## Other accepted product work

NotebookLM development is paused.
`REPORT_MVP_BASELINE_PASS`, `REPORT_MVP_AGNES_PASS`,
`REPORT_MVP_PIPELINE_RESUME_PASS`, `REPORT_MVP_DELIVERY_PASS`, and
`REPORT_MVP_OPERATIONS_PASS` are historical completed Goals.

The approved NotebookLM architecture is frozen in
`docs/superpowers/specs/2026-09-03-research-notebooklm-synthesis-design.md`.
NotebookLM runtime code exists, including pre-auth gates; its goal has not passed. The formal systemd service/timer remains unchanged.

### Local daily backtest WebUI: browser accepted

- Accepted layout baseline: `5118bd4ec9a082b45eacd0422b40e0452d3124c3`; main now serves
  `http://127.0.0.1:7231/` by FastAPI; the built React/Monaco assets are local.
- Browser strategy version save/reopen, report return with draft preservation,
  historical source/config restoration, menu navigation, explicit task errors,
  and actual page parameter effects are verified.
- Buy-and-hold: 59 daily records / 1 trade / 59 position rows. DMA: 20 / 4 / 9.
  Three-stock weekly rebalance: 16 / 7 / 48. All ran through the existing
  PostgreSQL Worker, InvestmentDataProvider and BulletTrade using local data.
- Restored historical rerun has the same result hash. Deliberate source failure
  and missing benchmark data display FAILED with an error, not a successful report.
- Native report initial capital/units and engine price-mode propagation are fixed.
  Missing/empty required report artifacts prevent SUCCESS. Infinite native metrics
  retain their meaning as JSON strings for PostgreSQL/API serialization.
- Actual operations, screenshots, run IDs, artifact hashes and constraints:
  [browser acceptance](acceptance/local-backtest/README.md),
  [manifest](acceptance/local-backtest/manifest.json).
- Local trusted single-user daily backtests only; no minute/live/post-adjusted
  execution or full-market/complete JoinQuant compatibility claim. Detailed native
  interactive chart assets still use CDN; the standard report embeds its images.
- Current targeted regression suite: 16 passed. Frontend build passed. Research
  daily service/timer configuration was not changed or re-accepted in this milestone.

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
- `REPORT_MVP_7D_LIVE_PASS` ended at `0 / 7` with
  `ABORTED_BY_PROVIDER_CUTOVER`. Its Agnes evidence remains preserved. A future
  NotebookLM seven-day observation begins only after formal provider cutover.

## Frozen Historical Facts

- BulletTrade WebUI/backtest has native report artifacts, reproducible snapshots,
  async worker recovery, and CI coverage. Its supported daily browser workflow
  is accepted in the completed WebUI milestone.
- Qlib research hardening and OOS tooling are complete historical work.
- Kronos Goals 0–2 have recorded data-audit, GPU-runtime, and pipeline
  evidence. Their data/real-assist limitations remain recorded.

## Historical verification (preceding research milestone)

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

## 7231 数据状态页面事实

正式端口已加载 datahub-v1 页面，任务 / Governor / 正式覆盖 / 折叠诊断分层展示；浏览器与 45 项 DataHub 单测通过。详情见 [布局验收](acceptance/datahub-v1/webui-7231-layout.md)。002504 的 SDK `NoneType` 解析异常曾错误打开 circuit，现已作为 `SYMBOL_DATA_ERROR` 审计并解除 false-positive cooldown；worker 正在从 `PENDING` 串行恢复。控制与发布完整验收未完成，Goal 仍为 IN_PROGRESS。
