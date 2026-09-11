# DataHub daily update remediation

**Goal:** Implement the supplied 2026-09-11 remediation on `main`, preserving existing releases and performance work.
**Architecture:** Reuse journal, Governor, RawStore, paired releases and provider. One update process owns writes; the UI reads saved summaries.
**Spec:** `/home/ken/下载/QuantRadar_DataHub_整改方案与Codex执行指令_2026-09-11.md`.
**Execution:** Inline, P0 → P1 → P2. No unrelated branch merges or new infrastructure.

## P0 — evidence and correctness
- [x] Preserve launcher modification and merge DataHub into main.
- [x] Export actual configured failure baseline, categories and legacy gap evidence.
- [x] Test and fix unknown-empty classification, deterministic retry, journal races and stale process state.
- [x] Stream candidate validation: real types, keys, values and hashes; bind results to inputs.

## P1 — update and publication
- [x] Inspect deployed Dolt version, branch, remotes, working state and read-only mode.
- [x] Add one update job, explicit sync/backfill/resume/repair semantics and target range.
- [x] Isolate invalid candidates; retain only eligible old data; validate fixed commits before pointer switch.
- [x] Verify update outcomes and economic-content idempotency with real/isolated checks.

## P2 — reads and usable page
- [x] Surface real base and supplemental coverage, update stages and grouped issues.
- [x] Pin supported supplemental accesses and enforce missing-range/field/PIT errors.
- [x] Validate UI, release refresh, historical replay and performance; label unexecuted checks explicitly.
- [ ] Record remaining source/deployment limitations, commit and push main.

## Constraints
No new source qualification, frozen BaoStock candidates, fabricated gap evidence, forced Dolt reset, or writes to base tables. Only configured trusted upstream fast-forward synchronization is permitted. Unknown data and unexecuted checks remain explicit. Each meaningful production change is checked with temporary-directory tests before live use.
