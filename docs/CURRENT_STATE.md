# QuantRadar2 Current State

Updated: 2026-10-09 (Asia/Shanghai). Current goal: [ACTIVE_PHASE](ACTIVE_PHASE.md). Authorized plan: [development plan](QUANTRADAR2_DEVELOPMENT_PLAN.md).

- Repository: D:/Projects/QuantDev/QuantRadar2; origin KenGGG/QuantRadar; observed baseline c950d67, main. Local development branch codex/quantradar2-workbench is active; no push.
- External BulletTrade: D:/Projects/BulletTrade; version 0.10.0; Python 3.12.15; imports from local source. Vendor version label: 0.9.2. Relevant file hashes and create_backtest signature differences are archived; external clean HEAD matches upstream main at audit time.
- Node 24.21.0, Git 2.56.0.windows.2 and npm.cmd 11.19.0 respond. npm.ps1 is blocked by execution policy. Frontend dependencies installed and production build passed.
- QMT historical daily/minute stock/ETF/index finite-sample connectivity passed. Research RPC 21 interfaces were called; limitations are archived in docs/acceptance/quantradar2-g0/qmt-research-21-20261009.json.
- Existing Gateway is ready but trading/cancellation are enabled. No trading operation was called. Separate data-only service on 58621 is running; offline rejection test and real health/data read passed.
- Old backend depends on InvestmentDataProvider, DataHub activation and maintenance locks; its existing results do not prove the new V2 path.
- Independent SQLite metadata/schema, API, FIFO worker and subprocess runner are implemented and G1 accepted. Runtime metadata is var/quantradar2/metadata.sqlite3; V2 API is 127.0.0.1:7242.
- The full V2 development plan and active goal files exist; first-release G0/G1/G2 execution is now the current objective. Historical V1 facts are preserved separately and are not current Windows acceptance evidence.

- Independent .venv-v2 installed; 10 V2 tests passed, pip check passed, V2 production build passed. G0/G1 accepted with recorded data limitations; G2 is active.
- Native daily buy-hold sample generated one simulated purchase, native reports and benchmark. API/direct CSV and metrics matched exactly. Browser save/run/restore/preview passed without page errors.
- Historical price limits unavailable from BigQMT; V2 omits limits only for native current-data field requests, allowing existing BulletTrade estimates. Precision of historical ST/listing rules is not qualified.
- Finite data freezing/replay, minute suite and full task failure/recovery acceptance are not yet completed.
