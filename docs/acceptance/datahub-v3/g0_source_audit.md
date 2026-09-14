# DataHub V3 P0 — G0 Source Audit

## Contract

Raw evidence records what a provider returned at `observed_at`. Canonical data
records QuantRadar's versioned interpretation of that receipt. PIT qualification
records whether that interpretation can be shown to have been available at a
historical time. They are separate facts.

The machine-readable receipt inventory is
[`g0_source_audit.json`](g0_source_audit.json). Raw response bytes are stored
content-addressably in the configured `DATAHUB_RAW_ROOT`, and are intentionally
not committed to this repository.

## Confirmed local adapter contracts

AKShare 1.18.94 exposes the following G0 adapters:

- `index_stock_cons_csindex`: source-declared `日期`, index code, constituent
  code and exchange. The date is retained as `source_date`; it is not assumed
  to be an effective date.
- `index_stock_cons_weight_csindex`: same identity fields plus `权重`; the
  source contract documents this as percent, so future canonical rows retain
  both `weight_raw` / `PERCENT` and `weight_fraction`.
- `index_component_sw`: component code, `最新权重` and `计入日期`. The latter is
  member-level evidence, while the former has no verified unit and remains raw.
- `stock_*_sheet_by_report_em`: balance sheet, income statement and cash-flow
  responses. Their current historical values are raw evidence only until
  statement-version and announcement/availability semantics are published.

## Current live evidence

On 2026-09-14, real raw responses were captured for CSI300, CSI500 and CSI1000
constituents and weights; a SW L1 (`801010`) component sample; and the three
statements of 600519.SH, 000333.SZ, 300750.SZ, 600036.SH and 601318.SH. The
machine receipt contains 24 captures because two interrupted attempts were
preserved independently rather than overwritten.

The observed balance-sheet schemas confirm the need for a small canonical
mapping: 319 fields for the ordinary-company samples, 221 for the bank and 253
for the insurer. CSI weights have a verified percent unit. SW's reported
“latest weight” remains raw because the source contract does not prove its unit.
All historical financial responses remain `PIT_PARTIAL`: a current API response
does not establish what prior revision was visible on the stated notice date.

## G0 exit criteria

G0 passed after raw evidence was retained for CSI300/500/1000, a SW L1 sample,
and all three statements for 600519.SH, 000333.SZ, 300750.SZ, 600036.SH and
601318.SH. The evidence records real returned columns, units and date semantics;
a successful function import was not treated as proof.
