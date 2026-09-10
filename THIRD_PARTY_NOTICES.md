# Third-party notices

## astock-data-toolkit

- Source: `https://github.com/tiantianlaolao/astock-data-toolkit`
- Commit: `80dbdba675201163b0d6ab36633971093f3b4be6`
- License: MIT, Copyright (c) 2026 北京天怡宝宝数字科技有限公司
- Reviewed source files: `download_astock_data.py`, `backfill_15y/backfill_15y.py`,
  `backfill_15y/orchestrator.sh`, `backfill_15y/merge_backfill.py`,
  `run_weekly_update.sh`.
- Local adaptation: `backend/quantradar/datahub/store.py` maps its progress,
  error, heartbeat, per-shard persistence, dry-run and single-instance patterns
  to QuantRadar's existing journal, staging and Dolt release model.
- Modifications: removes its Parquet/SQLite storage, all proxy manipulation,
  its data-source choices and fixed request intervals. QuantRadar keeps Dolt,
  one source lock and explicit gap states.

## baostock

- Source: `https://github.com/zxygithub/baostock`
- Commit: `eedcb785d10842347377c9c2990fad3c828ea90f`
- License: MIT, Copyright (c) 2026 正版生鱼片
- Reviewed source files: `src/downloaders/base.py`, `src/db_manager.py`,
  `scripts/check_data_integrity.py`, `scripts/fix_data_gaps.py`.
- Local adaptation: `backend/quantradar/datahub/governor.py` and
  `store.py` map its persistent request accounting, signal checkpoint,
  integrity and targeted-gap-repair patterns to upstream-neutral JSON state.
- Modifications: no BaoStock data source, login handling, SQLite store or
  `49000/day` setting is copied. QuantRadar retains bounded retries and its
  existing Dolt publication system.

Both upstream projects are MIT licensed. Their copyright and permission notices
apply to any copied or adapted substantial portions.
