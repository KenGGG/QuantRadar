# Low-Beta first-rebalance status repair

The strict low-Beta strategy needs same-day `is_st` and `tradestatus` for its
20 actual initial candidates on the previous trading day, `2023-08-31`.

One controlled BaoStock session fetched those 20 securities for that one date.
All raw responses were archived in RawStore and were checked against the
immutable base table before publication: **0 base-key overlaps** were found.
The resulting fixed release is `R3f2a0c82acf28962`; its status-patch dataset
contains 43 records (the prior 23 plus this 20-record repair).

With strategy version 141 (`低 Beta 策略 · 严格预检版`) and the same release,
the one-day `2023-09-01` backtest passed the first rebalance: it selected the
20 repaired candidates and produced 19 fills, with result hash
`6c25e895eb47dba10de0858af29bc02b2e8c41a369e1a610c76a15c2abcd3708`.

This proves only that first rebalance dependency.  The remaining monthly
status dates from the broader low-Beta window remain a separate pending gap;
this result does not claim all-window status coverage.
