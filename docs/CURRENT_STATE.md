# QuantRadar2 Current State

Updated: 2026-10-09 (Asia/Shanghai). Current goal: [ACTIVE_PHASE](ACTIVE_PHASE.md). Authorized plan: [development plan](QUANTRADAR2_DEVELOPMENT_PLAN.md).

- Repository: D:/Projects/QuantDev/QuantRadar2; origin KenGGG/QuantRadar; observed baseline c950d67, main. Local development branch codex/quantradar2-workbench is active; no push.
- External BulletTrade: D:/Projects/BulletTrade; version 0.10.0; Python 3.12.15; imports from local source. Vendor version label: 0.9.2. Relevant file hashes and create_backtest signature differences are archived; external clean HEAD matches upstream main at audit time.
- Node 24.21.0, Git 2.56.0.windows.2 and npm.cmd 11.19.0 respond. npm.ps1 is blocked by execution policy. Frontend dependencies installed and production build passed.
- QMT historical daily/minute stock/ETF/index finite-sample connectivity passed. Research RPC 21 interfaces were called; limitations are archived in docs/acceptance/quantradar2-g0/qmt-research-21-20261009.json.
- Existing Gateway is ready but trading/cancellation are enabled. No trading operation was called. Separate data-only service on 58621 is running; offline rejection test and real health/data read passed.
- Old backend depends on InvestmentDataProvider, DataHub activation and maintenance locks; its existing results do not prove the new V2 path.
- SQLite is authorized but the V2 database/schema/API/runner have not been implemented.
- The full V2 development plan and active goal files exist; first-release G0/G1/G2 execution is now the current objective. Historical V1 facts are preserved separately and are not current Windows acceptance evidence.

- Independent .venv-v2 installed; pytest isolation test 1 passed and pip check passed. G0 accepted with recorded non-core limitations; G1 is active.
