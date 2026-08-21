# QuantRadar 当前开发任务

文件：`docs/ACTIVE_PHASE.md`

**当前阶段：Kronos Goal 2 投资研究 Pipeline 已完成真实验收（GOAL2_ENGINEERING_PASS ✅）。Goal 0 的数据缺口仍存在，正式回测和实盘辅助门禁保持关闭。**

---

## 冻结声明与门禁重构（2026-08-22）

**基线冻结**：Goal 0/1/2 已合并入 `main@be495bb`，作为正式基线冻结。后续 Goal 必须从 `main`
**新建分支 + 新建 worktree** 开发，不复用旧 worktree/分支（避免基线漂移）。本变更在
`feat/kronos-gate-refactor` / `.worktrees/kronos-gate-refactor`。

**门禁重构（Goal 5A-refactor，已实施）**：复核 Kronos 官方要求后确认——Kronos `predict()` 仅依赖
OHLC + 时间戳（volume/amount 可选），**不需要** 000300 PIT / ST / 停牌 / 涨跌停 / 主数据 / 公司行为。
旧代码把「高保真回测 / 实盘辅助」所需数据错误提升为「Kronos 全局门禁」，并用
`raise RuntimeError("No exact 000300.SH PIT snapshot ...")` 把 Kronos 绑死到 000300 PIT。
现已修正：

- 门禁改为 **4 层能力模型** + 独立的 `csi300_pit_ready`：`kronos_signal_research_ready` /
  `realistic_backtest_ready`（fidelity=PARTIAL）/ `real_assist_data_ready` / `csi300_pit_ready`
  独立判定；单一能力缺失不再阻塞 Kronos 研究。
- 默认研究宇宙改为 **`all_a_liquid`**（由持续更新的 `final_a_stock_eod_price` 构造，PIT-free，
  沪/深 A 股，排除北交所与指数代码）。`list_signal_dates` / `collect_week_input_package` /
  `collect_real_input_package` 宇宙可配置（`--universe`）。
- 实测：`kronos_signal_research_ready=True`、`realistic_backtest_ready=True`（PARTIAL）、
  `real_assist_data_ready=False`、`csi300_pit_ready=PARTIAL`。
- **数据补齐降级为 Goal 5B**：仅用于提升 realistic / live 层级保真度，不再是 Kronos 研究的阻塞项。

**优先级（用户决策）**：门禁已开，Kronos 信号研究可立即推进；**不做 Goal 3/4、不做参数调优、不把
Kronos 结果包装为正式投资结论**，直到相关门禁达到目标保真度。详见 `docs/DATA_GATE_CLOSURE_PLAN.md`。

## Kronos Goal 2 验收（2026-08-21）

```text
闭环：investment_data -> 固定 Kronos-base CUDA -> Signal Artifact -> TopK Target Weight
      -> run_unified_backtest -> BulletTrade 原生报告
真实 PIT 信号：2022-06-01、2022-06-30
实际执行日：2022-06-02、2022-07-01（全部严格晚于信号日）
真实数据 commit：rlr4k90ir2ok2tggb2nflr83qntc5q2t（运行期间未变化）
模型路径：五条固定 seed；2022-06-30 在两次独立 SignalRun 的 prediction hash 完全一致
真实回测：35 个交易日；两次实际调仓；report.html、standard_report.html、metrics.json、trades.csv、daily_positions.csv 与 snapshot.json 均已生成
哈希链：prediction -> signals.parquet -> target_weights.parquet -> BulletTrade result_hash 已逐项核验
阶段标志：GOAL2_ENGINEERING_PASS

formal_backtest_ready = false
real_assist_data_ready = false
```

证据：`reports/kronos/goal2_engineering/`。入口：`make kronos-research-pipeline START=2022-06-01 END=2022-06-30`。

说明：该标志只证明工程闭环与可审计性，不证明信号有效、策略可正式回测或可用于实盘。后续 Goal 3 才实现 WebUI 工作区；Goal 4 才实现参数研究；Goal 5 才补齐数据。

## Kronos Goal 1 验收（2026-08-21）

```text
独立环境：.venv-kronos（主 .venv 不安装/导入 torch）
GPU：NVIDIA GeForce RTX 4070 SUPER；compute capability 8.9
Torch/CUDA/cuDNN：2.8.0+cu128 / 12.8 / 91002
Kronos source：67b630e67f6a18c9e9be918d9b4337c960db1e9a
Kronos-base revision：2b554741eca47781b64468546e77fef3e85130e6
Tokenizer revision：0e0117387f39004a9016484a186a908917e22426
模型锁：离线逐文件 SHA256 校验 PASS

真实输入：2022-07-01 PIT 沪深300；300 只候选，239 只合格，61 只排除
1只/1路径：0.322 秒；峰值 allocated VRAM 447.90 MiB
50只/1路径：0.919 秒；54.40 symbols/s；batch 50
239只/1路径：5.201 秒；45.95 symbols/s；batch 50
239只/5路径：22.559 秒；52.97 symbol-paths/s；batch 50
固定 seed 101 重跑：prediction hash 完全一致
batch 5 vs 逐只推理：rtol/atol=1e-5 内一致；最大相对差 1.92e-7
现有 PIT 129 周五路径估算：0.808 小时（仅限 2020-2022 可用覆盖，不外推缺失历史）

阶段标志：KRONOS_BASE_GPU_RUNTIME_PASS
注意：该标志只证明固定 Kronos-base 在真实 GPU 上可复现运行，不表示信号有效、回测可用或实盘可用。
```

产物：`models/kronos/kronos_model_lock.json`、`reports/kronos/runtime_smoke/`。
入口：`make kronos-runtime-setup`、`make kronos-gpu-smoke`。

下一动作：可以进入 Goal 2 的历史 RankIC、分组收益和信号排序工程；由于最新 PIT 成分缺失，Goal 2 的“最近2周真实运行证据”仍 BLOCKED，补齐数据前不得开放正式回测或实盘辅助。

---

## Kronos Goal 0 验收（2026-08-21）

```text
审计 Dolt commit：rlr4k90ir2ok2tggb2nflr83qntc5q2t（运行前后一致）
价格语义：PASS（30/30 只真实股票，none/pre/qfq/post/hfq 对账通过）
公司行为：PARTIAL（20 个真实候选事件；无独立事件类型、送转比例、现金与股数事实表）
沪深300 PIT：PARTIAL（20/20 个覆盖内周度对账通过，但 000300.SH 仅覆盖 2020-01-02..2022-07-01）
最新可交易状态：PARTIAL（价格至 2026-08-18；涨跌停至 2023-06-12；ST/tradestatus 至 2023-06-09；股票主数据至 2022-07-18）

price_semantics_ready       = true
corporate_action_ready      = false
pit_universe_ready          = false
latest_tradeability_ready   = false
signal_research_ready       = false
formal_backtest_ready       = false
real_assist_data_ready      = false

阶段标志：KRONOS_DATA_CONTRACT_AUDIT_COMPLETE
注意：该标志表示审计完整执行，不表示数据全 PASS。
数据后续：补齐/确认 000300.SH PIT 成分与公司行为、ST、停牌、涨跌停和股票主数据后，重新运行 make kronos-data-audit；这些门禁未通过前不得开放正式回测或实盘辅助。
```

产物：`reports/kronos/data_audit/`；入口：`make kronos-data-audit`。

---

## 〇、审计记录（BulletTrade WebUI 收口起点）

**原则**：BulletTrade = 回测与分析核心；QuantRadar = WebUI + API + 任务/结果管理。禁止重实现收益率/Sharpe/回撤/胜率/盈亏比等已有 BulletTrade 指标。

### A. BulletTrade 原生已提供（应直接复用，不要重造）
- `bullet_trade.core.engine.create_backtest(strategy_file, start, end, frequency, initial_cash, benchmark, log_file, extras)` → 返回 `results` 字典（含 `daily_records`/`trades`/`events`/`daily_positions`/`meta`/`summary`）。
- `bullet_trade.core.analysis.generate_report(results, output_dir, gen_csv, gen_html, gen_images)` → 写 `report.html`（详细交互报告：指标+曲线+月度热力图+Trades/Positions/Daily 表）、`metrics.json`、`risk_metrics.csv`、`trades.csv`、`daily_records.csv`、`daily_positions.csv`、`annual_returns/monthly_returns/open_counts/instrument_pnl` 的 CSV/PNG。内部 `calculate_metrics` 计算完整指标（策略收益/年化/基准/累计超额/最大回撤/最大回撤区间/最大回撤持续天数/夏普/索提诺/Calmar/胜率/盈亏比/交易天数）。
- `bullet_trade.reporting.generate_cli_report(input_dir, output_path, fmt, metrics_keys, title)` → 读目录内 `metrics.json`+`daily_records.csv` 生成聚宽风格 `standard_report.html`（13 项核心指标 + 净值/超额/回撤/月度热力图 4 张图，base64 内嵌）。其 `DEFAULT_METRICS_ORDER` 已精确覆盖目标要求。
- CLI 链路（`vendor/bullet-trade/bullet_trade/cli/backtest.py`）：`create_backtest() → generate_report() → generate_cli_report()`。

### B. QuantRadar 当前重复实现点（本次要消除）
1. **前端 `frontend/src/components/ResultsView.tsx` 用 React+ECharts 重算并绘制净值曲线/累计收益率/回撤**——这些 BulletTrade 原生报告已含，必须改为直接嵌入 BulletTrade `report.html`/`standard_report.html`（iframe），前端不再重算/重绘指标图。
2. **前端指标展示取 `snapshot.metrics`（`snapshot.py::compute_metrics` 仅 4 字段：final_total_value/total_return/max_drawdown/days）**——这是审计指纹用的极简指标，缺 Sharpe/Sortino/Calmar/胜率/盈亏比/超额/月度热力图。完整指标应来自 BulletTrade `metrics.json`。Snapshot/Audit 保留为附加审计信息，不替代原生 metrics。
3. **回测链未走 BulletTrade 原生报告管线**：`backend/quantradar/backtest.py::run_backtest` 用 `BacktestEngine(strategy_file=)` + `build_snapshot`，从不调用 `generate_report`/`generate_cli_report`，故从未产出 `report.html`/`standard_report.html`/完整 `metrics.json`。

### C. 统一方案（本次实施）
- 新增 `backend/quantradar/backtest_run.py`：`run_unified_backtest()` = 写版本化 `strategy.py` → `_FQ_LOCK` 设 `use_real_price`（fq）→ `create_backtest()` → `generate_report()` → `generate_cli_report()` → 写 `snapshot.json`（审计附加）→ 返回 run 目录与产物路径。
- `worker._run` 改走 `run_unified_backtest`；`runs/<run_id>/` 保存全部 BulletTrade artifact + snapshot.json；PostgreSQL 仅存 run_id/状态/策略版本/配置(含 run_dir/报告路径)/完整 BulletTrade metrics/result_hash。
- API 新增/完善：`POST /api/backtest/async`（已存在，补 fq/benchmark/strategy_name）、`GET /api/backtest/runs/{id}`（已存在，补 run_dir/报告路径/完整 metrics）、`GET /api/backtest/runs/{id}/report`（直接返回 BulletTrade HTML）、`GET /api/backtest/runs/{id}/artifacts`（产物清单）。
- WebUI：策略页保留 Monaco + 补 Benchmark/fq；提交走 async + 轮询状态 + 错误日志；成功后进入独立报告页（iframe 嵌入 BulletTrade HTML + 审计面板 + 产物清单）。
- 保留 Snapshot/Audit 作为附加信息（不替代原生 metrics）。

---

```text
目标：在「功能型 V1」达成的基础上，补齐工程与研究正确性加固，使系统达到可审计、可复现、
本地可信研究工具的安全底线。审查确认：当前为 FUNCTIONAL_V1（功能闭环可用），但尚非
「严谨研究型 V1」（数据层 2023 后残缺、复权口径/多模型/参数寻优等仍需深化）。
本阶段只做 5 件事，不堆新功能：
  1) 依赖可重建            PASS  HARDENING_DEPS_PASS ✅
  2) 测试库隔离+localhost  PASS  HARDENING_TEST_ISOLATION_PASS ✅
  3) 审计链                PASS  HARDENING_AUDIT_CHAIN_PASS ✅
  4) Qlib 防未来函数       PASS  HARDENING_QLIB_NOFUTURE_PASS ✅
  5) Worker 稳定性 + CI    PASS  HARDENING_WORKER_CI_PASS ✅
阶段标志：QUANTRADAR_FUNCTIONAL_V1_PASS ✅ 已达成（5 项 Hardening 标志全绿；make test /
make smoke 本机全量通过；GitHub Actions CI 已建）
```

---

# 一、目标

把「基于本地真实数据、可审计、可复现」从口号落到工程底线：

```text
数据正确性 > 可复现性 > 持久化 > 异步 > 安全。禁止向未知/未授权数据库写入（必须停止条件）。
```

本阶段收敛为 5 项加固（每项：开发→测试→修复→更新 CURRENT_STATE→commit→push→下一项）：

---

# 二、5 项加固（已全绿）

## 1) 依赖可重建 —— HARDENING_DEPS_PASS ✅
- `pyproject.toml` 补 `[project.dependencies]`（fastapi/uvicorn/sqlalchemy/psycopg2-binary/
  pandas/numpy/pydantic/python-dotenv/pyqlib/lightgbm/httpx/pytest，取自已验证版本）。
- 新增干净 `requirements.txt`（去本机绝对路径、bullet-trade 以 `-e ./vendor/bullet-trade`、
  剔无关包），`Makefile setup` 安装它 + 前端 `npm ci && npm run build`。
- `frontend/package.json` 补全 antd/@ant-design/icons/@monaco-editor/react/echarts/echarts-for-react/
  dayjs；`npm install` 重新生成 `package-lock.json` 使 `npm ci` 可复现；修复前端类型构建错误。
- `requirements.lock` 仅作开发机完整快照，不再用于安装。

## 2) 测试库隔离 + localhost 安全边界 —— HARDENING_TEST_ISOLATION_PASS ✅
- `storage.get_engine()` 优先 `QUANT_RADAR_TEST_PG_URL`（指向 `_test` 库），与正式库物理隔离。
- `storage.drop_all()` 对任何「库名不含 `_test`」的连接串一律拒绝（杜绝误 DROP 正式库）。
- 集成测试改用 `QUANT_RADAR_TEST_PG_URL`；未设置则整文件 skip，绝不回退到正式库。
- 本机已建专用测试库 `quantradar_test`。
- `quantradar.sh` 检测到 `HOST=0.0.0.0` 时强警告（`/api/backtest/strategy` 是无认证 RCE）。
- `README.md` 明确安全边界与测试库约定。

## 3) 审计链 —— HARDENING_AUDIT_CHAIN_PASS ✅
- `build_snapshot` config 补全 `security/amount/benchmark/extras`。
- 新增确定性 `snapshot_hash`（= H(config_hash, strategy_hash, data_asof, dolt_commit,
  provider_version)），与 `run_id`（每次唯一）/ `result_hash`（输出指纹）语义分明
  （见 docs/04 第九之一节）。
- 异步回测：用户策略源码先落库 `strategies` 表（source+strategy_hash），`backtest_runs.strategy_id`
  绑定之；内置策略 strategy_id 为 NULL（由 config 决定可复现）。
- 新增/加固单测：snapshot_hash 确定性、config 含 security/amount/benchmark、策略源码落库绑定。

## 4) Qlib 防未来函数 —— HARDENING_QLIB_NOFUTURE_PASS ✅
- `qml/bridge.py`：月度再平衡改为「严格早于交易日」取信号（`mask = index < day`），
  T 日信号留到 T+1，修复同日未来数据泄露；新增纯函数 `select_signal_date` + 单测。
- `qml/loop.py`：新增 `assert_segments_disjoint` 守卫，Train/Valid/Test 时间区间必须不重叠。
- `qml/dump.py`：用 `final_a_stock_eod_price.adjclose` 对 OHLC 做后复权调整（volume/amount 保持
  原始），避免除权除息跳变污染 Alpha158 标签与特征。

## 5) Worker 稳定性 + GitHub CI —— HARDENING_WORKER_CI_PASS ✅
- `worker.py`：异步执行改用固定大小 `ThreadPoolExecutor`（默认 4 线程），杜绝每次提交新建线程
  无限增长；进程重启时将遗留 `RUNNING` 恢复为 `PENDING` 并重新入队（单进程内保证最多一次重试）。
- `storage` 新增 `get_strategy` / `list_runs_by_status` 支撑恢复。
- 测试 `requires_dolt` 标记 + autouse 跳过：无 investment_data(Dolt)/PG 的 CI 环境自动 skip，
  纯逻辑测试照常运行，套件全绿。
- 新增 `.github/workflows/ci.yml`：后端（安装依赖 + `make test`）+ 前端（`npm ci && npm run build`）。

---

# 三、验收（本阶段完成）

```text
[HARDENING_DEPS_PASS]            fresh clone 经 make setup 可重建（依赖/前端可复现）
[HARDENING_TEST_ISOLATION_PASS]  测试仅用 _test 库；drop_all 拒绝非 _test 库
[HARDENING_AUDIT_CHAIN_PASS]     snapshot config 完整 + 策略源码落库 + hash 语义分明
[HARDENING_QLIB_NOFUTURE_PASS]   bridge 同日前视修复 + segment 守卫 + 复权训练
[HARDENING_WORKER_CI_PASS]       固定线程池 + 重启恢复 + GitHub Actions CI 绿
[PASS] git diff --check 无遗留空白错误
[PASS] 单一 commit 序列（#53~#57）
[PASS] push origin main
```

---

# 四、已知局限（严谨研究型 V1 的前置，本阶段未做）

```text
- 数据层 PARTIAL：价格至 2026-08-18，但 bao 的 ST/tradestatus/公司行为代理仅至 2023-06-09，
  涨跌停至 2023-06-12，股票主数据至 2022-07-18，000300.SH 成分仅至 2022-07-01。
- Kronos Goal 0 已统一复权契约：final OHLC 为 raw；hfq/post 使用 final.adjclose/close 因子；
  qfq/pre 必须显式给出参考日；volume/amount 不复权。旧的「final.close 已是连续复权价」结论失效。
- Qlib 仅最小闭环（Alpha158+LightGBM）；多模型/参数寻优/更严谨的样本外评估属后续研究。
- 单 uvicorn 进程模型；多进程水平扩展（分布式锁 FOR UPDATE SKIP LOCKED）不在本地工具范围。
```

---

# 五、下一阶段（已启动：严谨研究型 V1）

```text
「严谨研究型 V1」：在 FUNCTIONAL_V1 之上，补齐数据层完整性、统一复权口径、扩展 Qlib 研究，
并对关键结论做样本外稳健性验证。已据用户决策启动（AskUserQuestion：下一步=启动严谨研究型 V1；
数据缺口=标记待用户侧补齐，不阻塞、不伪造；研究范围=复权统一+列表补全、Qlib多模型+寻优、样本外稳健性验证）。
范围排除：选股+ST/停牌过滤（依赖待定数据，未选）、数据补齐本身（用户侧）。
```

---

# 六、BulletTrade WebUI 收口（BULLETTRADE_WEB_REPORT_PASS ✅）

把 QuantRadar 建成完整 BulletTrade WebUI：用户提交 JoinQuant 兼容策略源码 → 获得类似聚宽回测页的
完整 HTML 分析报告。**核心原则：禁止重实现 BulletTrade 已有指标能力（收益率/Sharpe/回撤/胜率/盈亏比等），
全部复用 `bullet_trade.core.engine` / `analysis` / `reporting`（`create_backtest` / `generate_report` /
`generate_cli_report`）。**

## 实施内容
- **统一回测链** `backend/quantradar/backtest_run.py::run_unified_backtest`：
  写版本化 `strategy.py` → `_FQ_LOCK` 设 `use_real_price`（fq 透传）→ `bootstrap_investment_data(set_active=True)`
  → `create_backtest()` → `generate_report()`（report.html/metrics.json/CSV/PNG）→ `generate_cli_report()`
  （standard_report.html）→ `build_snapshot_from_results` 写 `snapshot.json`（审计附加）→ 返回 run 目录与产物路径。
- **修复 BulletTrade 明确 bug（允许范围）**：`create_backtest(benchmark=...)` 参数长期未接线——
  `BacktestEngine.__init__` 未保存 `self.benchmark`，`_run_impl` 在 `load_strategy` 的 `reset_settings()` 后
  未重新注入基准，导致基准恒为 None、报告 `基准收益/累计超额收益` 永远 0。**修复**：引擎构造函数保存
  `self.benchmark`，并在 `load_strategy` 之后、若 strategy 未自行 `set_benchmark` 时重新注入（strategy 胜出）。
  实测修复后 `000300.XSHG` 基准收益 4.19%、累计超额 -2.47%（数据来自 investment_data 的 `SH000300` 指数行情）。
- **API 四端点** `backend/quantradar/api/app.py`：
  `POST /api/backtest/async`（补 fq/benchmark/strategy_name）、
  `GET /api/backtest/runs/{id}`（补 run_dir/报告路径/完整 BulletTrade metrics）、
  `GET /api/backtest/runs/{id}/report?which=full|standard`（直接返回 BulletTrade 原生 HTML），
  `GET /api/backtest/runs/{id}/artifacts`（产物清单，报告标注 is_report + 可访问 URL）。
- **WebUI 报告页** `frontend/src/components/ReportPage.tsx`：iframe 嵌入 BulletTrade `report.html` /
  `standard_report.html`，不重算指标；独立审计面板（`snapshot.environment`：provider/provider_version/
  dolt_commit/schema_hash/bullettrade_commit/quantradar_commit）；产物清单。策略页保留 Monaco + 补
  Benchmark/fq，提交走 async + 轮询状态 + 错误日志。
- **产物目录** `runs/<run_id>/` 保存全部 BulletTrade artifact（report.html / standard_report.html /
  metrics.json / daily_records.csv / trades.csv / daily_positions.csv / risk_metrics.csv /
  annual_returns/monthly_returns/open_counts/instrument_pnl 的 CSV+PNG / backtest.log / strategy.py /
  snapshot.json）。PostgreSQL 仅存 run_id/状态/策略版本/配置(含 run_dir 与报告路径)/完整 BulletTrade
  metrics/result_hash；大文件留文件系统，不入库。

## 验收（BULLETTRADE_WEB_REPORT_PASS）

```text
[BULLETTRADE_WEB_REPORT_PASS]
  1) 原生指标齐全（metrics.json 中文键，前端不重算）：
     策略收益 / 策略年化收益 / 基准收益 / 累计超额收益 / 最大回撤 / 最大回撤区间 /
     夏普比率 / 索提诺比率 / Calmar比率 / 胜率 / 盈亏比 / 交易天数  —— 全部非空
  2) 报告图完整（standard_report.html，聚宽风格）：净值 / 基准 / 超额 / 回撤 / 月度热力图 / 收益曲线
  3) 交易与审计产物齐全：Trades / Positions / Daily / Logs / 策略代码(参数) / Snapshot 审计
     （provider/provider_version/dolt_commit/schema_hash/bullettrade_commit/quantradar_commit）
  4) 报告 API 端到端：/report(full+standard) 返回 200 HTML 且含关键章节；/artifacts 列出全部产物；
     历史 Run 再次打开同一报告幂等（同一产物）
  5) Web 页面：frontend/dist 已构建；SPA 托管；ReportPage 进入构建产物（非死代码），
     依赖的报告/产物 API 契约（getRunReportUrl/standard_report）在场
  6) 自动化验收覆盖：tests/unit/test_bullettrade_web_report.py
     (A) 统一回测链真实策略端到端产出全部 BulletTrade 原生产物 + 指标覆盖目标全部项
     (B) PG 可用时 异步提交→落库→/report 与 /artifacts 端到端
     (C) Web 页面契约（构建产物 + ReportPage 编译进 bundle + SPA 路由）
[PASS] git diff --check 无遗留空白错误
[PASS] 单一 commit 序列（#70~#74）
[PASS] push origin main
```

## 收尾（5 项条件全部达成 ✅）

```text
WebUI 收口收尾 goal（CI绿 / artifact 查看下载 / Worker 恢复 fq / 删除 ResultsView / 浏览器实跑验收）全部达成：

① CI 修绿：CI 无 investment_data(Dolt) / PostgreSQL 时 backend（23 passed / 131 skipped，0 failed / 0 errors）
   + frontend（npm ci && npm run build）双 job 全绿；根因=3 个 Dolt 依赖测试缺 requires_dolt 标记
   + 因子研究模块级 fixture setup 先于 autouse skip 触发 ERROR，已修（test_web_workbench 补标记 +
   test_factor_research universe fixture 加 try/except skip 守卫）。

② artifact 文件查看/下载：新增 GET /api/backtest/runs/{run_id}/artifacts/{name:path} 单文件端点
   （按扩展名推断 Content-Type + 规范化路径前缀校验防目录穿越 400、缺失文件 404）；前端 api.ts 加
   getRunArtifactUrl，ReportPage 产物清单非报告文件链接到单文件端点（内联/下载，替代原先指向列表端点的死链）。

③ Worker 恢复 fq：worker._payload_from_record 从落库 config 还原 fq（none/pre/qfq/post/hfq），
   重启恢复（RUNNING→PENDING 重入队）不丢复权口径；全链 API submit(payload.fq) → config.fq →
   recover 重建 → run_unified_backtest(_FQ_LOCK + use_real_price 消费) 贯通；实跑验证
   run config.fq=qfq、snapshot.config.fq=qfq。

④ 删除旧 ResultsView：frontend/src/components/ResultsView.tsx 已删除（无残留引用），报告图改由
   ReportPage 直接 iframe 嵌入 BulletTrade report.html / standard_report.html（前端不再重算/重绘）。

⑤ 浏览器实跑策略最终验收：启动后端+前端，经浏览器等价流程（提交真实策略 600519.XSHG + 基准
   000300.XSHG + fq=qfq → 轮询 SUCCESS → 打开 BulletTrade 报告页 + 产物清单下载）跑通；
   实测 基准收益 4.19% / 累计超额收益 -2.47%，dolt_commit 入审计；report(full) 422KB / report(standard) 391KB 正常渲染。
```

## 封版（BULLETTRADE_WEBUI_FINAL_PASS ✅）—— 主线已封版

BulletTrade WebUI 主线封版，3 项必做条件全部达成，架构不再扩张：

```text
[BULLETTRADE_WEBUI_FINAL_PASS]
  1) REPORT_INLINE_PASS：GET /api/backtest/runs/{run_id}/report 内联返回 HTML（非附件下载）
     —— app.py 改 FileResponse(content_disposition_type="inline")；
        测试覆盖 which=full 与 which=standard：status==200 / content-type 以 text/html 起头 /
        content-disposition 含 inline（tests/unit/test_web_workbench.py::test_async_backtest_runs_and_queryable）。
        实跑验证：report?which=full 与 report?which=standard 均 200 + text/html + inline。
  2) WORKER_RESTART_RECOVERY_PASS：Worker 重启恢复覆盖 RUNNING + PENDING（原仅 RUNNING），
     _recovered 仅在 DB 扫描+恢复流程成功启动后设置；PG 暂不可用时 recover 返回 0 但不永久封锁后续恢复。
     —— worker.py::recover 改扫 ["RUNNING","PENDING"] 并后设 _recovered；storage.list_runs_by_status 支持状态列表。
        测试：test_worker_restart_recovery_runs_and_pending（1 RUNNING + 1 PENDING → 2 均 SUCCESS）、
              test_worker_recover_pg_unavailable_does_not_block（PG 不可用时 recover 返回 0 且 _recovered=False）。
  3) WORKER_FQ_RECOVERY_PASS：Worker 重启恢复保留 fq（none/pre/qfq/post/hfq 全 5 值），
     验证真实恢复出的任务仍用原始 fq（payload.fq == fq 且 config.fq == fq 且 snapshot.config.fq == fq），
     非仅字段存在性。
        测试：test_worker_restart_recovery_preserves_fq（5 fq 参数化）+ 
              test_worker_restart_recovery_pending_preserves_fq（PENDING fq=pre，逐 run_id 捕获）。
[QUANTRADAR_SMOKE_PASS] live-server e2e：提交真实 JoinQuant 兼容策略(600519.XSHG, fq=pre) → SUCCESS；
   report(full) 与 report(standard) 均 200+text/html+inline；config.fq=pre=snapshot.config.fq。
[CI_BACKEND_PASS] 后端 make test（无 Dolt/PG 等价 CI）：24 passed / 138 skipped，0 fail。
[CI_FRONTEND_PASS] 前端 npm ci && npm run build 绿（无源码改动）。
```

### 架构（封版定稿，不再扩张）
```text
investment_data (Dolt，本地真实数据，只读)
   → InvestmentDataProvider（接入+复权同源）
   → BulletTrade（create_backtest / 账户 / 成交 / 指标 / 原生 HTML 报告，禁止重实现）
   → QuantRadar WebUI / API / Worker / history Run / Audit
```
暂停清单（封版后不启动）：Qlib/ETF/因子研究/参数寻优/新模型/Agent/新交易引擎/新回测框架/任何无关新功能。
禁止项：重实现 BulletTrade 已有的回测/账户/订单/指标/报告能力。

---

# 七、严谨研究型 V1 子项（进行中）

## T1) 复权口径统一 + 同源验证 + 审计记录 fq —— RESEARCH_T1_FQ_PASS ✅
- `snapshot.py`：`build_snapshot` 增 `fq` 参数，写入 config（位于 benchmark 之后、seed 之前）。
- `backtest.py`：`run_backtest` 增 `fq: str = "none"`（可选 none/pre/qfq/post/hfq）；`_FQ_LOCK`
  线程安全切换 BulletTrade `use_real_price`（`_use_real_price = _fq != "none"`），整个回测体包在
  `with _FQ_LOCK: set_option("use_real_price", _use_real_price) ... finally: 还原`；两路径均透传 `fq`。
- `qml/bridge.py`：`run_target_weight_backtest` 默认 `fq="pre"` 并透传 `run_backtest(..., fq=fq)`
  （pre 与 Qlib 的 hfq 在同一窗口收益率等价，仅净值绝对水平缩放常数因子）。
- 后续 Goal 0 审计纠正：final.close 是 raw；T1 的 fq 配置与审计记录仍保留，但其“已连续复权”解释失效。
- 测试：`tests/unit/test_backtest_fq.py` 3 passed（fq 透传 config / 净值连续 <0.30 / none 与 pre 日收益率
  相关>0.999 且期末对齐<1%）。

## T2) 股票列表补全（Point-in-Time 宇宙近似）—— RESEARCH_T2_UNIVERSE_PASS ✅
- `provider.py` 增 `extended_universe`：从 final 聚合首/末现日补全 `ts_a_stock_list`（至 2022-07-18）
  之后的上市股，标注 `source='final_approx'` PARTIAL（非权威列表）；显式排除 `ts_index_weight`
  中的指数代码（final 表含指数行情，避免把指数当股票）；扫描区间限定在 [缺口起点, start] 缩小 GROUP BY。
- `qml/dump.py` `select_universe` 增 `use_extended`：将基础宇宙与补全标的**合并**为完整 PIT 宇宙后
  确定性排序取前 N 只（合并而非追加，保证 cap 内也能含补全标的）；`build_qlib_data`/`run_qml_pipeline` 透传。
- 连接加固：`config.read_timeout` 30s→120s；`connection.query` 对执行中断连自动重建并重试一次（只读安全）。
- 测试：`tests/unit/test_universe_extended.py` 3 passed（来源标注/PIT、合并宇宙含补全标的且非指数/非 ts 列表、
  确定性）。

## T3) Qlib 多模型 + 参数寻优 + walk-forward —— RESEARCH_T3_MULTIMODEL/GRID/WALKFORWARD/INIT_PASS ✅ (#60 已完成)
- 多模型探测可用性：`available_models()` 按真实 import 探测 lgb/xgb/mlp；本环境仅 `LGBModel`
  可用（`xgb` 缺 xgboost、`mlp` 缺 torch 时 `_get_model_class` 抛 `NotImplementedError`，绝不伪造）。
- `grid_search_qlib`：轻量网格寻优（超参组合），固定随机种子按 IC 选优，结果可复现（同输入同输出）。
- `walk_forward_qlib`：滚动窗口训练/验证/测试，每折 segments 不重叠（`assert_segments_disjoint` 防泄漏），
  固定 seed 可复现，输出各折样本外 IC。
- 进程初始化隔离（关键坑，已解决）：
  * 每个进程仅 `qlib.init` 一次（`RecorderInitializationError` 守卫）；跨目录请求仅重定向
    `C['provider_uri']={"day": new_dir}`，不重 init（同进程跨目录实测 dirA→dirB 切成功，train_samples 指向 B）。
  * `joblib_backend` 强制 `'threading'` 必须置于 `_ensure_qlib_init` **之后**设置——重定向
    `provider_uri` 会把它重置回默认 `'multiprocessing'`，否则 `inst_calculator` 在 loky 子进程里
    因缺已注册的 `C` 崩溃（`AttributeError: No such 'registered'`）。
  * 测试共享同一 qlib 目录（`tests/unit/_qml_helpers.build_shared_qlib_dir`），与真实
    「单目录/会话」用法一致，彻底规避跨函数重定向。
- 测试：`test_qlib_models.py`(4) / `test_grid_search.py`(2) / `test_walk_forward.py`(2) 共 8 passed。

## T4) 样本外稳健性验证 + 可复现报告 —— RESEARCH_T4_OOS_PASS ✅ (#62 已完成)
- `qml/oos.py` `run_research_oos`：端到端（grid_search_qlib in-sample 选优 + walk_forward_qlib 多折 OOS）
  → 结构化（JSON 可序列化）报告，含 `config` / `grid` / `folds` / `oos`(均值/标准差/正 IC 折占比
  hit ratio) / `environment`(git commit + qlib/lightgbm/numpy/pandas 版本 + python 版本)。
- 可复现：固定随机种子 + 报告内记录完整配置与运行环境，同输入产出逐字节一致 JSON。
- 不伪造：完全依赖真实 Alpha158+LGBModel，任一失败如实抛出；numpy 标量转 python 原生类型保证可序列化。
- `scripts/research_oos.py`：CLI，复用已有 `--qlib-data-dir` 或 `--build` 自动构建，产出 `<out>.json` + `<out>.md`；
  `render_oos_markdown` 渲染可读摘要（配置/聚合指标/各折明细/环境）。
- 测试：`test_research_oos.py` 2 passed（字段齐全且样本外 IC 有限；同输入两次运行 JSON 逐字节一致）。

## T5) 测试隔离 / CI / smoke 扩展 + 文档 —— RESEARCH_TEST_ISOLATION/MAKE_RESEARCH/SPEC_06_PASS ✅ (#63 已完成)
- 测试隔离纪律：所有依赖 investment_data 的研究测试均带 `@pytest.mark.requires_dolt`；
  `test_qlib_loop.py` 补齐标记，与 conftest autouse `_skip_without_dolt` 一致。
- CI 安全：`QUANTRADAR_FORCE_NO_DOLT=1` 模拟无 Dolt 环境，套件整体绿（requires_dolt 测试自动 skip，不崩溃）。
- `make research` 端到端研究链路：`scripts/research_oos.py --build` 构建 qlib_data → 网格+OOS 可复现报告
  （`reports/oos.json` + `reports/oos.md`）；修 Makefile 重复 target。
- 文档：`06_Qlib研究规范.md` 第八节落地「研究正确性规则」（不伪造 / 多模型探测 / 网格寻优 /
  walk-forward 防泄漏 / 可复现报告 / 进程初始化隔离 / 复权同源 / 测试隔离纪律）；研究范围标注 T1-T4 已实现。
- 最终验收：`make test` 全量（Dolt 可达）+ 模拟 CI（`QUANTRADAR_FORCE_NO_DOLT=1`）均绿。

```text
外部待定（用户侧，不阻塞）：数据补齐方案（ST/停牌/列表，来自只读 Dolt，本仓库无法补齐）。
元信息缺口：bao_a_stock_eod_info→2023-06-09；final_a_stock_limit→2023-06-12；ts_a_stock_list→2022-07-18。
价格+adjclose→2026-08-18；指数权重全表→2026-07-31，但 000300.SH→2022-07-01（不完整）。
```
