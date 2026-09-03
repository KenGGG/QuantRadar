# QuantRadar Active Phase

**Milestone:** `QUANTRADAR_RESEARCH_NOTEBOOKLM_PASS`
**Active Goal:** `NOTEBOOKLM_POLICY_RUNTIME_PASS`
**Status:** ACTIVE

`MULTIFORMAT_CONTENT_GATE = PASS`

`REPORT_MVP_YESTERDAY_DIGEST_PASS = PASS`

`REPORT_MVP_7D_LIVE_PASS = ABORTED_BY_PROVIDER_CUTOVER`

`NOTEBOOKLM_POLICY_RUNTIME_PASS = false`

## Scope

The only active work is the separately approved design and future validation of
the NotebookLM policy and isolated runtime using explicitly permitted
non-sensitive inputs.

```text
one fixed Notebook → exclusive workspace lock → reset
→ non-sensitive Source → READY → indexed fulltext
→ explicit-source chat and citations → persist evidence
→ bounded Conversation/Source cleanup → verify empty workspace
```

The frozen architecture is
`docs/superpowers/specs/2026-09-03-research-notebooklm-synthesis-design.md`.

The current Goal does not implement the formal QYJ pipeline, upload real QYJ
data, modify the formal systemd service/timer, or cut over Feishu delivery.

## Provider-cutover decision

The previous Agnes seven-real-operating-day observation was terminated by the
approved provider-cutover decision without being marked as a product failure:

```text
REPORT_MVP_7D_LIVE_PASS = ABORTED_BY_PROVIDER_CUTOVER
```

All Agnes code, results, and acceptance evidence remain preserved. The formal
user-level systemd configuration is unchanged by the architecture-documentation
change.

## Frozen product boundaries

- Reuse QYJ collection, Snapshot membership, original artifacts, MinerU,
  Canonical Markdown, source audit, Outbox, Feishu, and the read-only WebUI.
- Maintain one fixed dedicated Notebook; Sources and Conversations are
  temporary and QuantRadar remains the permanent source of truth.
- Do not add a second Notebook, sharding, Notebook archival, RAG, a vector
  database, an MCP Server, Weixin search, Celery, Redis, or a new task queue.
- Keep Kronos Goals 0–2, Kronos WebUI, BulletTrade, Qlib, frontend bundle
  optimization, ETF, live trading, and unrelated models frozen.

The only formal Research channels remain:

- `HOT` — 热门研报 — `hotReport=1`, `secondReportType=`.
- `STRATEGY` — 策略研究 — `secondReportType=10301,10302,10303`.
- `FINANCIAL_ENGINEERING` — 金融工程 — `secondReportType=10202,10203`.

Do not add or substitute `FIXED_INCOME`.

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
recoverable retry, and idempotent replay remain saved as structured evidence.

## Queued Goals

1. `NOTEBOOKLM_SOURCE_SYNC_PASS`
2. `NOTEBOOKLM_CHANNEL_SYNTHESIS_PASS`
3. `NOTEBOOKLM_SHADOW_ACCEPTANCE_PASS`
4. `REPORT_MVP_NOTEBOOKLM_CUTOVER_PASS`
5. `REPORT_MVP_NOTEBOOKLM_7D_LIVE_PASS`

## Current Goal gate

`NOTEBOOKLM_POLICY_RUNTIME_PASS = false` until a separately approved
implementation completes the non-sensitive runtime, fixed-Notebook binding,
workspace locking/reset, measured capacity, Source READY/fulltext, explicit
Source-ID chat/citations, bounded Conversation reset, credential redaction, and
verified Source/Conversation cleanup acceptance.
