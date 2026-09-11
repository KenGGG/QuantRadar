# Low-Beta status dependency plan

The strict low-Beta strategy (version 141) rebalances on the first SSE trading
day of every month.  At each rebalance it reads `is_st` and `tradestatus` for
the preceding SSE trading day and the CSI 300 constituents that the fixed base
release resolves for that date.

Read-only calculation against release `R3f2a0c82acf28962` and base commit
`uhdpedb4pr97ve80aq6nrabr66atsqtq` produced the following unfilled tail plan:

| item | value |
| --- | ---: |
| Monthly dependency batches | 38 |
| First status date | 2023-06-30 |
| Last status date | 2026-07-31 |
| Date × constituent keys | 11,400 |
| Unique constituents | 300 |
| Constituent snapshot used by this base | 2022-07-01 |

This is the correct scope for a low-Beta state repair.  It is not a request to
download all-market, all-trading-day status data.  The existing 20-record
2023-08-31 repair remains a separately verified first-rebalance subset.

The fixed base has no later CSI 300 constituent snapshot, so the plan cannot
claim monthly constituent-history completeness after 2022-07-01.  Each future
BaoStock retrieval must archive raw bytes, keep only absent base keys, validate
the source contract, and publish a new fixed supplemental release only after
the collected batch passes those checks.
