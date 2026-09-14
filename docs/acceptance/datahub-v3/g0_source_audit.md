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

On 2026-09-14, CSI300 constituent and weight responses were successfully
captured. A subsequent CSI500 request remained non-responsive in the local
network environment and was stopped without creating a partial fabricated
receipt. The remaining G0 probes must be retried by the explicit audit command
before G0 can pass.

This is a source-health observation, not a reason to mark the entire product or
the preceding FactorLab milestone blocked.

## G0 exit criteria

G0 passes only after raw evidence exists for CSI300/500/1000, a SW L1 sample,
and all three statements for 600519.SH, 000333.SZ, 300750.SZ, 600036.SH and
601318.SH; the evidence must record real returned columns, units and date
semantics. A successful function import is insufficient.
