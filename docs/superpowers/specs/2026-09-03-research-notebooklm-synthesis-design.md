# QuantRadar Research NotebookLM Synthesis Design

**Status:** FROZEN

**Milestone:** `QUANTRADAR_RESEARCH_NOTEBOOKLM_PASS`

**Active Goal:** `NOTEBOOKLM_POLICY_RUNTIME_PASS`

**Approved:** 2026-09-03

## Goal

Replace Agnes in the formal daily Research synthesis path with NotebookLM while
keeping QuantRadar as the permanent source of truth. NotebookLM is a temporary
daily analysis workspace: one dedicated Notebook persists; each run's Sources
and Conversations are temporary; every input identity, indexed-text snapshot,
citation, result, Digest, and audit record is persisted locally before cleanup.

The previous Agnes observation ends without product failure:

```text
REPORT_MVP_7D_LIVE_PASS = ABORTED_BY_PROVIDER_CUTOVER
```

All Agnes code, results, and evidence remain available as read-only history and
for explicit operator-controlled rollback. Never silently fall back to Agnes or
mix providers in one Digest.

## Frozen scope

Reuse the QYJ collector, Snapshot membership, original artifacts, MinerU,
Canonical Markdown, source audit, operation records, Outbox, Feishu delivery,
and read-only Research UI. The only formal channels remain `HOT`, `STRATEGY`,
and `FINANCIAL_ENGINEERING`; do not add `FIXED_INCOME`.

Do not add a second Notebook, Notebook sharding or archival, RAG, a vector
database, an MCP Server, Weixin search, a task queue, Celery, or Redis.

## Workspace lifecycle

NotebookLM is a temporary AI reading workspace, not a historical database.

```text
fixed Notebook
→ acquire exclusive notebook workspace lock
→ reset Sources and Conversation
→ load one target date's readable unique reports
→ wait for READY and snapshot indexed fulltext
→ isolated article and channel analysis
→ persist inputs, outputs, citations, and READY_CANDIDATE Digest
→ delete Conversations and Sources
→ verify source_count = 0 and no Conversation
→ atomically promote Digest to READY and reserve Outbox
→ release lock
```

The exclusive notebook workspace lock covers Reset, upload, READY/fulltext
audit, analysis, persistence, and Cleanup. No other NotebookLM run may inspect
or mutate the fixed Notebook while it is held. QuantRadar permanently retains
Snapshots, PDFs, extracted text, MinerU and Canonical Markdown, hashes, Source
Ledger, indexed fulltext, citations, results, Digest, and audit records.

## Runtime and credentials

Use the typed async API from the pinned PyPI release
`notebooklm-py==0.8.2` in `.venv-notebooklm`; do not install it in the main
environment or from upstream `main`. One worker process owns one event loop and
one `NotebookLMClient`. QuantRadar exchanges atomic JSON files with the worker.

Gate 0 tests Web and Android Backends with non-sensitive data and selects one
from real auth, upload, fulltext, citation, reset, and cleanup evidence. Runtime
fallback between Backends is forbidden.

Use a dedicated Google account. Credentials remain outside Git in a mode-0700
profile directory with mode-0600 files. Logs and evidence redact cookies,
tokens, master tokens, authorization headers, and credential paths.

## Fixed binding and crash-safe recovery

One permanent binding key, `research_daily_digest`, stores provider, full
remote Notebook ID, fixed title `QuantRadar Research Daily Digest`, Backend,
provider version, state, and timestamps. Normal lookup uses only the full ID.

`NOTEBOOK_MISSING` is valid only when the provider positively proves the bound
ID does not exist. Authentication, permission, network, timeout, rate limit,
decode, and API-drift errors retain the binding and never create a Notebook.

Replacement creation requires a durable recovery intent committed before the
remote create call. It records binding key, exact title, attempt identity, and
state. Crash recovery may resolve only by the permanent binding key or exact
full-title match:

- zero exact matches: create once or resume the recorded attempt;
- one exact match: verify it and atomically bind its full ID;
- multiple exact matches: stop with `NOTEBOOK_AMBIGUOUS`.

Never fuzzy-match or arbitrarily select a Notebook. Complete the recovery intent
only after readback and binding commit.

## Mandatory reset and local idempotency

Every invocation acquires the workspace lock and performs recovery before
checking for reusable local output:

1. Fetch the bound Notebook by full ID.
2. List and delete every residual Source with bounded retries.
3. Re-list until `source_count = 0` or the reset deadline expires.
4. Resolve and delete the current Conversation with bounded retries.
5. Re-query until no current Conversation remains or the deadline expires.

Delete/reset operations use at most three attempts with 1, 2, and 4 second
backoff. Source reset has a 120-second deadline and Conversation reset has a
60-second deadline. Failure is `NOTEBOOK_DIRTY` and blocks the run. Even an
identical local READY Digest must pass this health recovery before reuse or
delivery. After reset, an
identical date, Manifest, provider, Backend, prompt, and schema may reuse the
local READY result without remote upload or analysis.

## Manifest and Source capacity

The immutable daily Manifest stores schema, target date, provider, version,
Backend, Notebook ID, three-channel membership and order, deduplicated reports,
each report's Source kind and input hash, and prompt/schema versions. Its
canonical `input_manifest_hash` versions local runs; it never creates a new
Notebook.

Gate 0 must measure and prove:

```text
actual_source_capacity
>= historical_max_daily_readable_unique_reports + configured_safety_margin
```

Derive the historical maximum from stored three-channel Snapshots and readable
Source accounting. The initial
`QUANTRADAR_NOTEBOOKLM_SOURCE_SAFETY_MARGIN` is 10. Gate 0 proves capacity by
loading enough generated non-sensitive test Sources to reach the historical
maximum plus 10, then deletes them and verifies an empty workspace. Record the
margin and evidence. If this is unproven or a run
exceeds capacity, stop with `SOURCE_CAP_EXCEEDED`. Never create another
Notebook, shard, omit, or select a subset.

## Report accounting and Source attempts

Every readable unique report in the three target-date channels must produce one
selected READY Source. Cross-channel duplicates upload once while retaining all
memberships and platform orders.

Attempt candidates in order:

```text
PDF → WEIXIN_TEXT → HTML_URL → QYJ_AUTHENTICATED_TEXT
```

A candidate succeeds only after READY and indexed-fulltext validation. Fallback
is allowed only to an already audited candidate. If a remote ID exists for a
failed candidate, delete and verify it before trying the next.

Persist every attempt with `attempt_index`, report ID, Source kind, memberships,
orders, local input hash, remote Notebook/Source IDs and title, remote state,
indexed-fulltext path/hash/count, `selected_for_analysis`, `fallback_reason`,
READY time, and deletion status/error/time. Exactly one attempt may be selected
per run and report.

## Input contracts

### PDF

Upload the original PDF with `add_file`; title it
`[QR-{report_id}] 标题｜机构｜发布日期`. Do not upload MinerU or Canonical
Markdown as the NotebookLM PDF input. Retain the original PDF, SHA-256, page
metadata, MinerU, Canonical Markdown, and source audit locally.

### Weixin

For a real `mp.weixin.qq.com` permanent URL, reuse the installed `url-md`
command directly; do not run `wexin-read-mcp`. Parse title, author,
`publish_time`, `canonical_url`, optional `cover_url`, and Markdown body. Upload
title, author, time, original URL, and body with `add_text`. Use Source title
`[QR-{report_id}] 标题｜作者或公众号｜发布日期`.

### Public HTML URL

Use `add_url` only after safety validation. Allow only HTTP(S) public Internet
targets. Reject localhost, loopback, link-local, private, carrier-grade NAT,
multicast, reserved or internal DNS results, user-info credentials, QYJ
authenticated hosts/paths, and temporary sensitive signed URLs. Revalidate
every redirect and DNS resolution. Record the normalized URL without sensitive
query values. The Source must reach READY and pass fulltext validation.

### QYJ authenticated text

If no earlier candidate works, use the authorized persistent browser profile to
read QYJ locally. Upload title, institution or author, date, QYJ source
description, and Markdown body with `add_text`. Never transmit QYJ cookies,
tokens, headers, browser profile data, or authenticated credentials.

## READY and indexed-fulltext gate

Wait with `wait_until_ready` or `wait_all_until_ready` and require:

```text
ready_count + failed_count = expected_unique_report_count
```

Formal synthesis requires 100% READY coverage. Otherwise persist only
`DRAFT_PARTIAL`; do not reserve Outbox.

For every READY Source, call `get_fulltext()` and atomically save the complete
indexed fulltext under the Research data root before remote deletion. Store its
path, SHA-256, character count, and quality result. The initial minimum is 200
non-whitespace characters after frontmatter removal; content must also contain
more than the normalized Source title. Reject empty, login/error, title-only,
or below-threshold content. MinerU and NotebookLM text need not be byte-identical.

Source READY polling uses a 900-second per-run deadline. A timeout is recorded
per Source and participates in complete READY-or-failed accounting.

## Conversation isolation

Omitting `conversation_id` can still extend the current Conversation. Therefore
every article batch and channel synthesis performs:

```text
resolve current Conversation
→ bounded delete and re-query until absent
→ ask with explicit source_ids and no prior conversation_id
→ persist result, citations, and returned conversation_id
→ bounded delete of that ID and re-query until absent
```

A single unverified delete is not a reset. Failure is
`CONVERSATION_RESET_FAILED`. Channels never share a Conversation. The final
Digest is composed locally without a cross-channel NotebookLM request.

## Analysis and citation contracts

Process each channel in platform order in batches of 12–20. Each batch receives
only its Source IDs and returns, per report: report ID, title, one-line summary,
key points, core conclusion, method or logic, risks or limitations, and
citations.

Expected and returned report IDs must match exactly. Every report has at least
one citation, and its article summary may cite only its mapped Source. A bounded
repair addresses only invalid or missing Sources.

Each channel then uses a fresh Conversation and exactly its Source IDs to
produce overall summary, major themes, important views, consensus,
disagreements, new changes, risks, follow-up points, and citations. Every
citation must belong to that channel's Source set.

Before deletion, permanently save each citation's `source_id`,
`citation_number`, `cited_text`, `start_char`, `end_char`, `chunk_id`, `score`,
and `report_id` mapping. After cleanup, citation resolution may not depend on
remote Source availability.

## Minimal persistence

Add four tables only:

1. `research_provider_bindings`: fixed identity and recovery intent.
2. `research_notebook_runs`: Manifest, versions, status, validation, versioned
   Digest, primary error, and Cleanup result.
3. `research_notebook_sources`: one row per Source attempt with membership,
   identity, indexed snapshot, selection, fallback, and deletion evidence.
4. `research_notebook_answers`: article, repair, and channel outputs, citations,
   coverage, and Conversation identity.

Do not add duplicative provider-run, Notebook-binding, article-summary, or
Digest-version tables. Existing Agnes tables and `research_daily_digests`
remain historical. The NotebookLM run owns the versioned Digest; read APIs
select the active READY run and expose earlier results as history.

## Digest, Cleanup, and delivery

The deterministic Digest stores provider/version/Backend, Manifest hash,
Source accounting, citation coverage, the three channel summaries and article
indexes, and exceptions.

After all local inputs, indexed fulltexts, outputs, citations, and validations
commit, save it as `READY_CANDIDATE`. Then delete exact run Conversations,
delete every Source attempt, list the fixed Notebook, and require zero Sources
and no current Conversation. Persist Cleanup counts, status, and errors.

Only successful Cleanup permits one transaction to promote the Digest to
`READY` and reserve Outbox. Cleanup failure blocks Feishu. Failure paths make a
best-effort Cleanup in `finally`; Cleanup errors never overwrite the primary
pipeline error. The next run always begins with dirty-workspace recovery.

Outbox keys remain `research-digest:<target_date>:<digest_hash>`. A no-report
Digest is valid only when all three collections succeeded and all upstream
counts are zero.

## Errors

At minimum distinguish:

```text
AUTH_REQUIRED
NOTEBOOK_MISSING
NOTEBOOK_AMBIGUOUS
NOTEBOOK_DIRTY
SOURCE_CAP_EXCEEDED
SOURCE_UPLOAD_FAILED
SOURCE_READY_TIMEOUT
SOURCE_PROCESSING_FAILED
INDEXED_CONTENT_INVALID
HTML_URL_REJECTED
CHAT_RATE_LIMITED
CHAT_EMPTY
OUTPUT_PARSE_FAILED
COVERAGE_INCOMPLETE
CITATION_MISSING
CITATION_SOURCE_MISMATCH
CONVERSATION_RESET_FAILED
SOURCE_DELETE_FAILED
PROVIDER_API_DRIFT
```

Auth, permission, network, rate-limit, and API-drift errors never masquerade as
Notebook absence.

## Read-only WebUI

Keep the four Research tabs. Overview shows provider, Backend, Notebook health,
READY/citation coverage, and Cleanup. Report list shows selected Source kind,
attempts, READY/fulltext, analysis, citation, and membership. Report detail
shows local assets, indexed snapshot, NotebookLM output, citations, hashes, and
truncated remote IDs. Daily Digest shows Manifest, accounting, three channels,
exceptions, and history. Never expose a clickable Google Notebook URL or full
Notebook ID.

## Sequential Goals

1. `NOTEBOOKLM_POLICY_RUNTIME_PASS`: non-sensitive runtime only; verify pinned
   package, credentials/redaction, both Backends, binding/recovery, workspace
   lock/reset, measured capacity, PDF/Text/URL, READY/fulltext, explicit-source
   chat/citations, bounded Conversation reset, Cleanup, and an empty Notebook.
2. `NOTEBOOKLM_SOURCE_SYNC_PASS`: implement Manifest, four tables, selection,
   safe URLs, snapshots, accounting, capacity, fallback cleanup, and idempotency
   with authorized QYJ inputs.
3. `NOTEBOOKLM_CHANNEL_SYNTHESIS_PASS`: implement article batches, channel
   synthesis, repair, validation, cleanup-gated Digest, UI, and Feishu dry-run.
4. `NOTEBOOKLM_SHADOW_ACCEPTANCE_PASS`: at least three real dates; save but do
   not formally deliver NotebookLM output; compare Agnes independently.
5. `REPORT_MVP_NOTEBOOKLM_CUTOVER_PASS`: switch formal Digest/Outbox/Feishu;
   retain Agnes only for explicit rollback.
6. `REPORT_MVP_NOTEBOOKLM_7D_LIVE_PASS`: begin a new seven-real-day observation
   after cutover; earlier Agnes days do not count.

## Acceptance matrix

| Property | Required evidence |
| --- | --- |
| Fixed identity | One permanent binding key and one verified full remote ID |
| Exclusion | One lock covers Reset through verified Cleanup |
| Health | Every invocation proves zero Sources/no Conversation before reuse or work |
| Capacity | Measured capacity covers historical maximum plus safety margin |
| Membership | 100% accounted across the three formal channels |
| Sources | Every readable unique report has one selected READY Source |
| Attempts | Every attempt, fallback, selection, and deletion is persisted |
| Indexed text | Full local snapshot, hash, count, and quality per selected Source |
| Article index | 100% coverage with correctly mapped citations |
| Channels | Three isolated syntheses using explicit Source IDs |
| Citation durability | Complete citation fields remain resolvable after deletion |
| Digest | `READY_CANDIDATE` promotes only after verified Cleanup |
| Delivery | No Outbox for partial, blocked, dirty, or Cleanup-failed runs |
| Idempotency | Identical local READY result skips remote work after health recovery |
| Provider separation | No mixed Digest and no silent fallback |
| Cleanup | Zero Sources and no Conversation after success |
| Secrets | No credential leakage in Git, logs, evidence, or APIs |
| Shadow/live | At least three shadow dates and seven post-cutover live days |

## Current execution boundary

Only `NOTEBOOKLM_POLICY_RUNTIME_PASS` is active. Until this specification is
reviewed and a separate implementation plan is approved, do not implement
NotebookLM business code, set up or authenticate the runtime, upload any file,
modify the formal systemd units, or start Goal runtime operations.
