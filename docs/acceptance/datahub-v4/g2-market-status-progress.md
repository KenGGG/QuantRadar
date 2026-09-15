# G2 market trade-status progress

Recorded 2026-09-15 against fixed base commit `uhdpedb4pr97ve80aq6nrabr66atsqtq`.

- The status worker re-audits each claimed task at its release before contacting BaoStock, keeps only response rows in the returned field-level gaps, stores the raw response, publishes an additive candidate, and re-audits the resulting release.
- `000001.SZ` published 753 rows from raw receipt `e3419011849107f742e898ae84d759c9ca4244ccd6042e3753fe7f16acfa343c` and completed at `R57f372ec0f422c62`.
- Subsequent bounded batches reached `Rc02b494fe397bcac` / `oa4im51n4ir5vqek3308245pbpheugjh`. The persisted historical queue then contained 11 completed tasks, 3 quarantined source limitations, and 5,535 pending checks; no task remained running.
- `000003.SZ` has no BaoStock records for either status field from 2002-06-17 through 2026-09-11 after its single returned row. `000004.SZ` ends at 2026-07-13 and `000005.SZ` at 2024-04-26. Each has exact field/date gaps and a source-limitation reason in the durable queue; no missing row was inferred to mean normal trading or non-ST.

This is progress evidence only. G2 remains in progress until the market queue is exhausted or every residual source limitation has been classified and the full fixed-release coverage report is produced.
