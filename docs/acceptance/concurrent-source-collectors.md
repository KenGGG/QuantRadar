# Concurrent source collectors acceptance

- release: `R8057b38dbba4d3ad`
- base_commit: `ggclaf52m1n8nsmfm0mbr0987q0uhegs`
- supplemental_commit: `8tm5ipqaganavte88nopthk24kmqijb9`
- supplemental_dolt_clean: `True`
- publication: `no concurrent publishing observed; all Supplemental Dolt writes and release changes use datahub-publish.lock`

## Live collector evidence

- BaoStock pid: `303123`
- BaoStock heartbeat: `2026-09-16T16:12:10.185258+08:00`
- BaoStock status: `RUNNING`
- BaoStock journal: `/data/quantradar_data/daily-update.json`
- Eastmoney pid: `385159`
- Eastmoney heartbeat: `2026-09-16T09:36:14.694628+00:00`
- Eastmoney phase: `download`
- Eastmoney journal: `/data/quantradar_data/journals/valuation_daily-mvp.json`

BaoStock status maintenance and Eastmoney valuation backfill were simultaneously live with distinct PIDs, journals and heartbeats. Collection is source-scoped; a staged collector waits for `datahub-publish.lock` and resumes publication from its durable staging file without another upstream request.
