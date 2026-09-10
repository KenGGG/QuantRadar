# Current State

`docs/ACTIVE_PHASE.md` is the sole source of truth for the current goal. This
file records present facts, not plans or chronological logs.

## Repository

- Branch: `main`
- Remote backup: `origin/main` (baseline `3c87bb2`).
- HEAD: the current commit on this branch (`git rev-parse HEAD`).
- Local runtime state under `data/runtime/` is ignored and is not source data.

## Active Product Work

`REPORT_MVP_ENGINEERING_PASS`, `REPORT_MVP_WEB_VISIBILITY_PASS`, and
`REPORT_MVP_YESTERDAY_DIGEST_PASS` are complete and merged to `main` through
PR #3 (merge commit `7ba6cff`). The Agnes seven-day observation was terminated
by the approved provider-cutover decision and is recorded as
`REPORT_MVP_7D_LIVE_PASS = ABORTED_BY_PROVIDER_CUTOVER`; this is not a product
failure. `LOCAL_DAILY_BACKTEST_BROWSER_ACCEPTANCE_PASS` and milestone
`QUANTRADAR_LOCAL_BACKTEST_WEBUI_PASS` passed for the previous layout. The active
Goal `JOINQUANT_LAYOUT_BROWSER_ACCEPTANCE_PASS` passed by explicit user acceptance
on 2026-09-09. Layout work is closed; see
[acceptance record](acceptance/local-backtest/layout-user-acceptance.md).
The sole active Goal is `DATAHUB_INGESTION_MVP_PASS`; the former
`DATAHUB_REPRODUCIBLE_PIT_V1_PASS` and
`DATAHUB_GOVERNED_REPRODUCIBLE_V1_PASS` are superseded and are not PASS
results. MVP permits explicit `PARTIAL` releases with coverage and gaps; the
later Research Coverage Goal owns complete 2016 and delisted-security coverage.
Gate 0 is complete: `investment_data` was audited read-only at Dolt commit
`dje7kjb4gb27khhfmqncnfhf00n9igcg`, and real probes of the three approved
source interfaces established the documented `PARTIAL` PIT limitations. The
facts and boundaries are in [DataHub V1 evidence](acceptance/datahub-v1/README.md).
`/data/quantradar_data` is now owned by `ken:ken` (mode `0750`) and has an
empty independent Dolt repository served locally at `127.0.0.1:3308` by the
enabled user service `quantradar-datahub-dolt.service`. The limited real
validation release is `Rb60ab5f94b2a612b`; it pairs base commit
`dje7kjb4gb27khhfmqncnfhf00n9igcg` with supplemental commit
`4qrt5p86jdqpp4l2b0sm8d2r0o2fn7em`. The timer unit is installed but disabled until the DataHub branch
is integrated into the service working tree. BaoStock real requests are
suspended. Its former probes, `10002007` and `10001011` failures, 623
incomplete unpublished shards, journal, raw hashes, and error evidence are
frozen and excluded from canonical data and releases. `current_release`
remains the limited validation release; no DataHub V1 acceptance claim is
made. V1 valuation canonical semantics are `pe_ttm`, `pb_mrq`, `ps_ttm`, and
`pcf_ocf_ttm`: the old planned `pcf_ncf_ttm` is not a semantic alias and is
out of scope.
The governed Eastmoney MVP completed real interruption/resume and targeted
repair acceptance, then expanded through a 500-symbol stage. The current
remaining-universe process is running serially under the shared Governor.
At the last verified status it had 976 `COMPLETE`, 123 `NOT_COVERED`, 3
`FAILED`, and 3,813 `PENDING` shards. No new DataHub release has been
published.
The first governed Eastmoney A0 probe of required date `2016-01-04` returned
`success=false`, `code=9201`, `message=返回数据为空`, and `result=null` after
one controlled retry. Its rejected 89-byte response is content-addressed as
`ea6528a2204b61a7ee34683a73ca00f8afdc86aadf3f765d4dae39bbfb19dbe7`; the
acceptance record is `acceptance/datahub-v1/eastmoney-a0-2026-09-09.json`.
This historical source limitation is recorded as `PARTIAL`; it does not block
the approved ingestion MVP or its later release gates.
Under the later approved Source Qualification revision, Eastmoney official
per-symbol qualification also failed: 600519 and 000001 start at 2018-01-02,
and delisted 600005 failed. SSE lifecycle qualification succeeded, including
600005 in 159 delisted rows, but both SZSE qualification calls failed with TLS
EOF. The complete records and source gap report are in
`acceptance/datahub-v1/`; no valuation or complete lifecycle source is approved
for complete historical coverage; those facts remain explicit `PARTIAL` gaps.
NotebookLM development is paused.
`REPORT_MVP_BASELINE_PASS`, `REPORT_MVP_AGNES_PASS`,
`REPORT_MVP_PIPELINE_RESUME_PASS`, `REPORT_MVP_DELIVERY_PASS`, and
`REPORT_MVP_OPERATIONS_PASS` are historical completed Goals.

The approved NotebookLM architecture is frozen in
`docs/superpowers/specs/2026-09-03-research-notebooklm-synthesis-design.md`.
NotebookLM runtime code exists, including pre-auth gates; its goal has not passed. The formal systemd service/timer remains unchanged.

### Local daily backtest WebUI: browser accepted

- Runtime version: `5118bd4ec9a082b45eacd0422b40e0452d3124c3`, served at
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
