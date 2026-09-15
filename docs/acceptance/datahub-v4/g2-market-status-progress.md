# G2 market trade-status progress

Recorded 2026-09-15 against fixed base commit `uhdpedb4pr97ve80aq6nrabr66atsqtq`.

- The status worker re-audits each claimed task at its release before contacting BaoStock, keeps only response rows in the returned field-level gaps, stores the raw response, publishes an additive candidate, and re-audits the resulting release.
- `000001.SZ` published 753 rows from raw receipt `e3419011849107f742e898ae84d759c9ca4244ccd6042e3753fe7f16acfa343c` and completed at `R57f372ec0f422c62`.
- Subsequent bounded batches reached `Ra3aa859825d6c140` / `j1sqlsc000tsfmposh27ed8o1n5v7egc`. The persisted historical queue now contains 64 completed tasks, 34 tasks satisfied without a repeat source request, 23 quarantined source limitations, and 5,428 pending checks; no task is running.
- A resumed Worker binds every execution to the release current at claim time while retaining its planned release as evidence. This closed seven tasks whose rows had already been published by an interrupted batch without contacting BaoStock again.
- The Worker now fetches a bounded batch through one BaoStock login while preserving per-security raw receipts and errors. If the external execution window interrupts a batch, its next exclusive run automatically returns incomplete claims to `PENDING` and re-audits them.
- The user-level `quantradar-datahub.service` and `quantradar-datahub.timer` were enabled on 2026-09-15, sharing the user systemd scope that owns both Dolt SQL servers. The active timer invokes the dedicated `maintain-market-status` coordinator at 20:00 Asia/Shanghai with an infinite service start timeout; it runs the 20-trading-day current window and one 50-task historical batch. The dedicated mode explicitly skips valuation and industry collection.
- A persisted user-timer catch-up run completed on 2026-09-15 in `mode=status`: it verified base commit `0o6tgnmq5vabt3orqrk8rhqptniae26l`, refreshed the 5,899-security master, processed five current-window tasks and 50 historical tasks, and produced release `R91ec6235708e3d10`. The run recorded valuation and industry as `NO_CHANGE`; it did not start the legacy valuation transport. That run also exposed that a status patch could retain a prior paired base commit, so the coordinator now publishes a base-only release before its status audit when the fixed pair differs. The follow-up run recorded aligned base release `Rbe776ee098dcec6b` before entering its bounded status workers.
- The aligned follow-up completed with release `Rb7a2cd281c8e2ebe`, pairing the verified `0o6tgnmq5vabt3orqrk8rhqptniae26l` base commit with supplemental commit `e65blig93qrt9br7dskcp3oscrcmprhb`. Its five current tasks were satisfied without a source request; the historical worker reached 136 complete tasks, 34 satisfied tasks, 26 source-limitation quarantines, and 5,353 pending checks. No status task remained running.
- Daily target selection now requires both an open calendar date and base-price coverage through that date. A wall-clock cutoff cannot create a status task for a trading day whose source facts have not arrived.
- `000003.SZ` has no BaoStock records for either status field from 2002-06-17 through 2026-09-11 after its single returned row. `000004.SZ` ends at 2026-07-13 and `000005.SZ` at 2024-04-26. Each has exact field/date gaps and a source-limitation reason in the durable queue; no missing row was inferred to mean normal trading or non-ST.

This is progress evidence only. G2 remains in progress until the market queue is exhausted or every residual source limitation has been classified and the full fixed-release coverage report is produced.

## 2026-09-15 fixed-release current-window audit

The new read-only `market-trade-status-report` scanned the entire SH/SZ master
in bounded 25-security partitions. It does not create or modify queue tasks.
At `R05b433fd8803f501` (base `0o6tgnmq5vabt3orqrk8rhqptniae26l`,
supplemental `66fg9p699hveeka64udf0h5u4bimcsdu`), the 2026-08-18 through
2026-09-14 correction window had 5,556 supported SH/SZ securities, zero
lifecycle-unknown securities, and 343 explicitly unsupported BSE securities.
The lifecycle-qualified denominator was 208,552 fields; 17,764 were valid and
190,788 remained missing (8.51777973838659%). The exact 10,428 compressed
field intervals, contract version, release and commits are preserved in
[`g2-current-window-R05b433fd8803f501.json`](g2-current-window-R05b433fd8803f501.json).

This is a real coverage result, not a queue proxy: the sparse current-window
coverage is expected while the bounded five-task worker continues to consume
the 5,551 pending per-security checks. It is explicit evidence that G2 has not
passed.

## 2026-09-15 complete lifecycle-range audit

The same read-only report was run for every open SSE trading date from
1990-12-19 through the fixed base-price target 2026-09-14. It scanned the
5,556 SH/SZ securities in bounded 50-security partitions at
`R05b433fd8803f501` and did not enqueue or execute repair work. Its
lifecycle-qualified denominator is 36,959,510 fields: 29,812,010 are valid,
7,147,500 are missing, and coverage is 80.6612695893425%. The remaining facts
are compressed into 32,690 field intervals. All 343 BSE securities remain
explicitly `UNSUPPORTED`; no SH/SZ lifecycle denominator is unknown.

The exact fixed-release evidence, including every interval and the paired Dolt
commits, is [g2-full-coverage-R05b433fd8803f501.json](g2-full-coverage-R05b433fd8803f501.json).
The report process had emitted a parseable final JSON response but failed to
exit its interpreter; the user-scoped transient unit was stopped after the
evidence was validated. This does not change any source, queue, or release.

## 2026-09-15 bounded follow-up maintenance

The deployed user-level coordinator completed job
`update_059b5dc6f5b64f6fb1d00dda567a7042` in `mode=status` at
2026-09-15T12:07:03+08:00. All five claimed current-window tasks were
re-audited as `SATISFIED` without a repeat BaoStock request. The historical
worker claimed 50 checks, staged 31 source responses, completed 21 tasks,
left 18 retryable checks pending, and quarantined 11 no-row source responses.
It published 15,935 validated fill-only rows at `R77e0dde27449d342` with
supplemental commit `id9v6i459efka9l102lrt018uj9rbg39`; validation found zero
overlaps with base rows. The durable historical queue afterwards recorded 180
complete, 34 satisfied, 45 quarantined, and 5,290 pending tasks, with none
running.

## 2026-09-15 current-window throughput verification

After raising the bounded current-window batch to 50 securities, job
`update_88514d5c01df40499e8bb6be60efe83b` completed successfully. It claimed
50 current tasks: five were already satisfied and 44 completed after publishing
825 validated rows at `R1d298d6ecf938d14`. Its sequenced historical batch
claimed 50 tasks and published 25,896 rows at final release
`Rb9b7f3acc2fdab9c`. That release contains 605,926 supplemental trade-status
rows, up from 580,030 at the preceding current-window release, verifying that
the historical publish inherited rather than replaced the 825 current-window
rows. Both validations found zero base overlaps. The current queue is now 44
complete, five satisfied and 5,507 pending; the historical queue is 210
complete, 34 satisfied, 53 quarantined and 5,252 pending, with none running.
