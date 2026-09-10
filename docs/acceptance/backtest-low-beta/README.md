# Low Beta backtest investigation — 2026-09-10

The affected runtime is `.worktrees/datahub-v1`, serving port 7231.
Run `run_52057738341d4aa2906372fd60596345` uses strategy 138 and release
`Rb60ab5f94b2a612b`, for 2020-01-01 through 2026-08-31.
The run is advancing, not deadlocked. During verification it reached trading day
993/1615 (2024-02-01). Its final report has not yet been verified.

A count-limited price request fetched all prior limit-price rows, then discarded
all dates outside the returned price index. Bound that second query to the actual
price index; skip it for empty prices. Preserve missing limit prices as NaN.
A real 600011.XSHG one-day request at the same release took 2.575 seconds before
and 0.087 seconds after; pandas assert_frame_equal passed. This is a query timing,
not a full-strategy speedup claim.

Both editor and report now refresh the last 64 KiB of logs every five seconds.
The report shows current simulation date/day/total; the editor exposes a progress
link while running. The percentage represents the day currently being processed,
not report-generation completion. Built assets are served live. The existing
Python process still has its original provider implementation loaded; it was not
restarted because that would replay the user's in-progress long backtest.

Verification:

- New regression fails before the fix and passes afterward; covers bounded dates,
  missing limit rows and an empty price result.
- Targeted suite: 14 passed, 5 skipped (dedicated PostgreSQL test URL absent).
- Frontend typecheck/build passed; existing bundle size warning remains.
- Actual browser: editor restoration, live logs, progress navigation, periodic HTTP
  206 log reads, and no report-page JavaScript errors passed.
- Original strategy source, release and cash, with only dates narrowed to
  2023-09-01–2023-09-28: 44.94 seconds, 20 daily rows, 19 trades, 380 positions,
  full and standard reports generated. Artifacts are in
  `/tmp/quantradar-low-beta-check/low_beta_september_check`.
- Result hash: `e24bd0d3d892ddc26c5aeafcd2b78c343e380432ebef251caa6aef1f8e07a745`.

This maintenance fix does not pass or replace the active DataHub goal.
