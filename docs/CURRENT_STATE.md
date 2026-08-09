# 当前状态

文件：`docs/CURRENT_STATE.md`

> 系统「记忆」，由 Codex 在每次 ACTIVE_PHASE 完成后维护。只记录**现在的事实**，不写流水账（历史在 Git）。
> 本文件由 Phase -1/0 审计首次填充。下一阶段以新的 ACTIVE_PHASE.md 为准，禁止自动进入。

---

# 当前阶段

```text
当前阶段：Hardening 完成 → FUNCTIONAL_V1_PASS ✅（功能型 V1）→ 严谨研究型 V1 完成 QUANTRADAR_RESEARCH_V1_PASS ✅（T1/T2/T3/T4/T5 已完成）→ BulletTrade WebUI 收口 BULLETTRADE_WEB_REPORT_PASS ✅（统一回测链 + 报告 API + BulletTrade 原生报告页；暂停 Qlib/ETF/模型/寻优/因子等新开发）
  1) 依赖可重建            PASS  HARDENING_DEPS_PASS ✅（pyproject 补依赖 / 干净 requirements.txt / Makefile setup 装前端 / 前端依赖补全）
  2) 测试库隔离+localhost  PASS  HARDENING_TEST_ISOLATION_PASS ✅（TEST 库隔离 + drop_all 拒绝非 _test 库 + 0.0.0.0 强警告）
  3) 审计链                PASS  HARDENING_AUDIT_CHAIN_PASS ✅（config 完整 + 策略源码落库 + run_id/snapshot_hash/result_hash 语义分明）
  4) Qlib 防未来函数       PASS  HARDENING_QLIB_NOFUTURE_PASS ✅（bridge 同日前视修复 + segment 守卫 + 复权训练）
  5) Worker 稳定性 + CI    PASS  HARDENING_WORKER_CI_PASS ✅（固定线程池 + 重启恢复 + GitHub Actions CI）
阶段标志：QUANTRADAR_FUNCTIONAL_V1_PASS ✅ 已达成（5 项 Hardening 标志全绿；make test / make smoke 本机全量通过；CI 已建）
降级说明：原 QUANTRADAR_V1_PASS 更名为 FUNCTIONAL_V1_PASS——功能闭环已可用，但尚非「严谨研究型 V1」
  （数据层 2023 后残缺、多模型/参数寻优未做）。严谨研究型 V1 已启动：T1 复权口径统一已完成。
  【实测纠正旧认知】final_a_stock_eod_price.close/open/high/low 本身已是连续复权价（除权缺口已消除），
  600519 在 2023-2024 区间 fq='none' 与 fq='pre' 日收益率完全一致（none_min=pre_min=-0.0742，
  期末对齐 0.0000%，除权日候选 0）→ 回测腿（读 final.close）与 Qlib 训练（读 final.adjclose 后复权）
  天生同源连续复权，旧 summary「回测腿原始价 vs Qlib 复权价口径未统一」不实。两者已统一，无除权假跳变。
  故 T1 交付定位为：复权口径 fq 配置化（run_backtest/run_target_weight_backtest 支持 none/pre/qfq/post/hfq）
  + 审计 config 记录 fq + 线程安全切换 use_real_price（_FQ_LOCK），而非「修复假跳变」。
最近完成（Hardening）：pyproject/requirements/Makefile/frontend 依赖可重建；storage 测试隔离；snapshot config+策略落库+hash 语义；
  qml bridge/loop/dump 防未来函数；worker 固定池+重启恢复；tests requires_dolt 跳过；GitHub Actions CI。
QuantRadar 根 commit：见 git log（origin=KenGGG/QuantRadar）
BulletTrade 快照 base commit：be0451b（记录于 BASELINE.md；vendor/ 无 remote、无 .git）
```

---

## 当前可用（PASS）

```text
BulletTrade Ubuntu Core      PASS  （bullet-trade 0.9.2；BacktestEngine import OK；lab --diagnose OK）
QuantRadar Git 基线          PASS  （fork 为 vendor/bullet-trade 快照，QuantRadar 根自有仓库）
项目内 Python .venv          PASS  （python3.12.3；bullet-trade 以 editable 装入，指向 vendor/bullet-trade）
investment_data 可访问       PASS  （Dolt SQL server 127.0.0.1:3307，只读 SELECT 正常）
A 股日线                     PASS  （final_a_stock_eod_price，1990-12-19..2026-08-04，6129 标的）
交易日历                     PASS  （ts_trade_day_calendar，is_open=1 共 8797 日，1990-12-19..2026-12-31）
指数权重                     PASS  （ts_index_weight，6 指数，2005-04-08..2026-06-30）
指数成分                     PASS  （由 ts_index_weight 按 index_code 派生 stock_code）
涨跌停                       PASS  （final_a_stock_limit，pre_close/up_limit/down_limit）
ST 标记                      PARTIAL（bao_a_stock_eod_info.is_st ∈ {0,1}；bao 源仅至 2023-06-09）
Provider 源码审计             PASS  （7 问已回答，见下「Provider 机制」）
Generic Provider Registry    PASS  （Phase 1 实现：register_data_provider / unregister_data_provider，经 _create_provider 统一入口，见下）
Registry lifecycle           PASS  （Phase 1.1：unregister 清 Registry/cache/auth；overwrite 清旧 cache 并用新 factory；active global 不热切换；13/13 测试通过）
InvestmentDataProvider base  PASS  （Phase 2A：只读 Dolt 连接 + symbol mapping + get_trade_days / get_all_securities(PIT) / get_security_info / get_index_stocks(PIT) / get_index_weights(PIT)；38/38 QuantRadar 测试通过）
get_price 日频原始价          PASS  （Phase 2B：final_a_stock_eod_price，fq='none'，open/high/low/close/volume/amount 直读，绝不使用 adjclose；单/多证券、start/end/count/fields、与原表抽样对账一致；17 个新增测试通过）
JoinQuant 兼容核心            PASS  （Phase 3：frequency 别名 d/day/1d->daily；字段别名 money->amount；fq='none' 原始价 + fq='pre'/'post' 等价原始价 LIMIT 透传，绝不伪造复权；get_price/history/attribute_history 经 Generic Provider Registry 接入 BulletTrade 引擎；与原表抽样对账一致，close≠adjclose 已验证；13 个新增 JQ 兼容测试通过）
真实 A 股回测                PASS  （Phase 4：BacktestEngine 经 Provider 跑通 600519.XSHG 2023Q1，无异常；daily_records/持仓/资产曲线来自真实价，与原表对账一致；防未来数据生效；get_price 扩展 high_limit/low_limit（final_a_stock_limit）/paused（volume==0 派生）；新增 3 个回测 + 3 个字段测试通过）
真实复权（前/后复权）          PASS  （Phase 5：fq='post'/'hfq' 后复权 close 精确等于原表 adjclose；fq='pre'/'qfq' 前复权以 pre_factor_ref_date/窗口末日为基准（基准日 close==原始）；因子由 adjclose/原始价真实推导，绝不伪造；仅缩放 OHLC，volume/amount 保持原始；新增 4 个对账测试通过）
Snapshot / 可复现             PASS  （Phase 6：quantradar.snapshot 固化回测环境与 daily_records 结果指纹；save/load round-trip；同配置两次运行逐日一致；指纹对配置敏感；新增 3 个测试通过）
完整 Snapshot / Audit          PASS  （Closing Phase 1：FULL_AUDIT_REPRO_PASS；build_snapshot 补齐 snapshot_id / config_hash / strategy_hash / result_hash / metrics / environment(dolt_commit, schema_hash, provider_version, bullettrade_commit, quantradar_commit)；确定性测试验证 NAV/Trades/Positions/Metrics 一致 + 审计指纹一致；backend/quantradar/audit.py 采集 Dolt HEAD 与数据表 schema 哈希；3 个测试通过）
FastAPI 服务基础             PASS  （Phase 7：/api/health、/api/price、/api/backtest、/api/snapshot save/load；全程经 InvestmentDataProvider 读真实数据，无 mock；新增 4 个 TestClient 测试通过）
中文 WebUI / 主线闭环        PASS  （QUANTRADAR_STOCK_V1_PASS：浏览器策略回测 + 实验 + Web 构建 均已就位）
浏览器策略回测                PASS  （Phase 8/STOCK_V1：/api/backtest/strategy 接受 JoinQuant 兼容用户源码，引擎注入 get_price/order_target/log/g/run_daily 等全局，经 InvestmentDataProvider 跑真实数据；复用 BulletTrade 撮合/账户/订单/成交/调度，不重实现；3 个 TestClient 测试通过）
实验管理 API                  PASS  （/api/experiments 列表 / /api/experiments/{name} 加载 / /api/experiments/save 保存，复用 backend/quantradar/experiment 本地 JSON）
Web 构建（frontend/dist）     PASS  （offline 自包含中文 SPA：行情查询 / 策略回测(可编辑代码) / 实验列表，消费 /api/*，无 CDN、无构建步骤；GET / 优先托管；满足「Web build 成功」）
React+TS+Vite 源码脚手架      PASS（frontend/ 已是完整工作台：AntD 布局 + Monaco 策略编辑器 + ECharts 净值/收益/回撤图 + 数据状态/策略回测/运行记录/实验对比；npm install && npm run build 已生成 dist 并由 GET / 托管；后端已挂载 /assets 静态目录 + SPA 兜底路由，修复资源 404 白屏）
QuantRadar Provider bootstrap IMPLEMENTED（Phase 2A：backend/quantradar/bootstrap.py 显式 register + set_active + 校验 name）
公司行为 + ST（Phase 5 补全）  PASS  （CORPORATE_ACTION_ST_PASS：get_split_dividend 据 bao_a_stock_eod_info 真实 preclose 缺口还原每股税前红利，与原始表逐行对账；get_extras('is_st'/'tradestatus') 直读真实列，df=True/Dict 两形态；9 个新测试 + 3 个 registry 测试通过）
因子研究（Phase 9 无依赖）    PASS  （backend/quantradar/research 复用 bullet_trade.research.factors.evaluation.evaluate_factor_performance；动量因子 ic_mean≈0.0146、rank_ic_mean≈0.0065（HS300 子集）；长表 [date,code,factor,forward_return]；IC/RankIC/分层/多空 齐全；4 个测试通过）
Experiment 实验管理（Phase 9） PASS  （backend/quantradar/experiment；基于 Snapshot 指纹的本地 JSON 存证与对比；save/load/list round-trip、不同配置不同指纹、同配置可复现、从 BacktestEngine 构造；3 个测试通过）
Make / Smoke（QUANTRADAR_SMOKE_PASS） PASS  （Makefile：setup/test/smoke/dev；scripts/smoke.py 全链路 数据→回测→快照→API→Web 入口 通过；无 mock）
Qlib import                  PASS  （pyqlib 0.9.7 已装入 .venv）
PostgreSQL + Worker          PASS  （PERSIST_WORKER_PASS：backend/quantradar/storage.py 5 表 Strategy/BacktestRun/Experiment/Snapshot/Metrics + SQLAlchemy CRUD；backend/quantradar/worker.py 异步 submit→run_id→后台线程 run_backtest(BulletTrade)→落库；API /api/backtest/async + /api/backtest/runs/{id} + /api/backtest/runs；复用 run_backtest，禁止重实现；集成测试连本机 1Panel 专用库 quantradar 跑通真实回测落库，4/4 通过）
React WebUI（工作台）         PASS  （WEB_WORKBENCH_PASS：frontend/ React+TS+Vite+AntD+Monaco+ECharts；数据状态/策略编辑器(回测提交)/运行记录(异步状态轮询)/实验对比；净值·累计收益·回撤 ECharts 图 + Metrics + 持仓 + 成交 + 运行流水 + 审计环境；GET / 托管构建产物；test_web_workbench 5/5 通过）
Qlib 数据构建                  PASS  （build_qlib_data：由 investment_data(Dolt) 真实导出 qlib_data；字段 open/high/low/close/volume/amount/vwap，VWAP=amount*10/volume（与官方 investment_data 一致）；FileCalendar/FileInstrument/FileFeature Storage 写二进制；Point-in-Time 宇宙防幸存者偏差；tests/unit/test_qlib_loop.py 验证）
Qlib 最小闭环                  PASS  （QLIB_BULLETTRADE_LOOP_PASS：Alpha158 + LightGBM → Train/Valid/Test 时间切分 → Prediction → calc_ic IC/RankIC → TopK 等权 Target Weight → 月度再平衡策略 → BulletTrade 账户回测；无未来数据（标签为 Alpha158 Ref($close,-2)/Ref($close,-1)-1，按点对齐）；mlflow 经 exp_manager 重定向临时目录不污染仓库；tests/unit/test_qlib_loop.py 2/2 通过）
依赖可重建                    PASS  （HARDENING_DEPS_PASS：pyproject[project.dependencies] 补齐；干净 requirements.txt；Makefile setup 装前端；frontend package.json 补全 antd/monaco/echarts 并构建）
测试库隔离 + localhost 边界    PASS  （HARDENING_TEST_ISOLATION_PASS：集成测试仅用 QUANT_RADAR_TEST_PG_URL 的 _test 库；drop_all 拒绝非 _test 库；quantradar.sh 对 0.0.0.0 强警告）
审计链                        PASS  （HARDENING_AUDIT_CHAIN_PASS：snapshot config 含 security/amount/benchmark/extras；新增确定性 snapshot_hash；用户策略源码落库 strategies 并绑定 backtest_runs.strategy_id）
Qlib 防未来函数               PASS  （HARDENING_QLIB_NOFUTURE_PASS：bridge 同日前视修复 index<day；loop segment 不重叠守卫；dump 用 adjclose 后复权训练避免除权跳变）
Worker 稳定性 + CI            PASS  （HARDENING_WORKER_CI_PASS：worker 固定 ThreadPoolExecutor + 重启恢复 RUNNING→PENDING 重入队；tests requires_dolt 自动 skip；GitHub Actions CI 后端测试+前端构建）
复权口径配置化 + 同源验证       PASS  （RESEARCH_T1_FQ_PASS：run_backtest/run_target_weight_backtest 支持 fq∈{none,pre,qfq,post,hfq}，审计 config 记录 fq，_FQ_LOCK 线程安全切换 use_real_price；实测 final.close 已连续复权，回测腿与 Qlib 训练同源，无除权假跳变；test_backtest_fq.py 3 passed）
股票列表补全（PIT 近似宇宙）    PASS  （RESEARCH_T2_UNIVERSE_PASS：extended_universe 从 final 聚合首/末现日补全 ts_a_stock_list(至2022-07-18)缺口上市股，排除指数代码，标注 source='final_approx' PARTIAL；select_universe(use_extended) 合并为完整 PIT 宇宙；read_timeout 升至120s + query 断连自动重试验证加固；test_universe_extended.py 3 passed）
Qlib 多模型探测                PASS  （RESEARCH_T3_MULTIMODEL_PASS：available_models 按真实 import 探测 lgb/xgb/mlp；本环境仅 LGBModel 可用（xgb 缺 xgboost、mlp 缺 torch 则 _get_model_class 抛 NotImplementedError，绝不伪造）；run_qlib_loop(model='lgb') 跑通产出有限 IC/RankIC + 158 维特征 + Target Weight；test_qlib_models.py 4 passed）
Qlib 网格寻优                  PASS  （RESEARCH_T3_GRID_PASS：grid_search_qlib 固定 seed 遍历超参组合、按 IC 选优、结果可复现（同输入同输出）；2x2 网格 4 组；test_grid_search.py 2 passed）
Qlib walk-forward 滚动窗口     PASS  （RESEARCH_T3_WALKFORWARD_PASS：walk_forward_qlib 逐折 Train/Valid/Test 不重叠（assert_segments_disjoint 防泄漏）、固定 seed 可复现、各折样本外 IC 有限；test_walk_forward.py 2 passed）
Qlib 进程初始化隔离            PASS  （RESEARCH_T3_INIT_PASS：qlib 初始化唯一入口 _ensure_qlib_init（build_qlib_data 与 run_qlib_loop 都经它，杜绝重复 init 把全局 C 重置/锁定→loky 子进程 No such 'registered' 崩溃）；joblib_backend 强制 'threading' 规避重定向重置 multiprocessing；lgb 强制 num_threads=1 保证固定 seed 逐位可复现；build_qlib_data 重建前清空 calendars/instruments/features 子目录避免 qlib 合并旧数据的 float32 TypeError；实测跨目录重定向因 InstrumentProvider/CalendarProvider 缓存不随 provider_uri 失效会读到陈旧 instruments——故测试统一单目录/进程（与真实用法一致），彻底规避）
样本外稳健性验证              PASS  （RESEARCH_T4_OOS_PASS：run_research_oos 端到端（grid 选优 + walk_forward 多折 OOS）→ 结构化可复现报告（JSON+MD），含 config/grid/folds/oos(均值/标准差/正IC占比)/environment(git commit+版本)；固定 seed 同输入同输出；scripts/research_oos.py 复用/自动构建 qlib_data 产出双报告；test_research_oos.py 2 passed）
研究测试隔离纪律              PASS  （RESEARCH_TEST_ISOLATION_PASS：所有依赖 investment_data 的研究测试均带 @pytest.mark.requires_dolt；conftest autouse _skip_without_dolt 在 Dolt 不可达时自动 skip；QUANTRADAR_FORCE_NO_DOLT=1 可模拟无 Dolt CI 环境整体绿；测试共享 qlib 目录避免跨进程重定向）
研究链路 make 目标           PASS  （RESEARCH_MAKE_RESEARCH_PASS：Makefile 增 research 目标，端到端跑 scripts/research_oos.py --build 产出 reports/oos.json+md；修 Makefile 重复 target）
Qlib 研究规范(06) 更新         PASS  （RESEARCH_SPEC_06_PASS：docs/06_Qlib研究规范.md 第八节落地研究正确性规则——不伪造/多模型探测/网格寻优/walk-forward防泄漏/可复现报告/进程初始化隔离/复权同源/测试隔离纪律；研究范围标注 T1-T4 已实现）
BulletTrade WebUI 收口          PASS  （BULLETTRADE_WEB_REPORT_PASS：统一回测链 run_unified_backtest 复用 create_backtest→generate_report→generate_cli_report，产出 BulletTrade 原生 report.html/standard_report.html/metrics.json/CSV/PNG/日志/snapshot 于 runs/<run_id>/；指标全来自 BulletTrade 原生（策略收益/年化/基准/超额/最大回撤/区间/夏普/索提诺/Calmar/胜率/盈亏比/交易天数），前端 iframe 嵌入不重算；API /api/backtest/async + /runs/{id} + /runs/{id}/report(full|standard) + /runs/{id}/artifacts；ReportPage 审计面板 + 产物清单；修复 BulletTrade 明确 bug——create_backtest(benchmark=) 参数长期未接线致基准恒为 0，已修复（引擎保存 self.benchmark 并在 load_strategy 后重新注入，实测 000300.XSHG 基准收益 4.19%/累计超额 -2.47%）；tests/unit/test_bullettrade_web_report.py 6 passed + test_persist_worker 续绿）
BulletTrade WebUI 最终封版        PASS  （BULLETTRADE_WEBUI_FINAL_PASS：主线已封版。3 项必做全部达成——
  (1) 报告内联显示 REPORT_INLINE_PASS：GET /api/backtest/runs/{id}/report?which=full|standard 返回 text/html + Content-Disposition: inline（FileResponse 加 content_disposition_type="inline"），前端 iframe 直接渲染 report.html/standard_report.html；test_async_backtest_runs_and_queryable 对两种报告断言 status=200/content-type=text/html/content-disposition 含 inline；实测 live 服务器 full/stand 均返回 inline。
  (2) Worker 重启恢复双覆盖 WORKER_RESTART_RECOVERY_PASS：recover() 现扫描 ["RUNNING","PENDING"] 并全部重入队重跑；_recovered 仅在 DB 扫描成功启动后才置位——PG 暂不可达返回 0 且不永久阻断未来恢复；保持 PostgreSQL + 固定 ThreadPoolExecutor（无 Celery/Redis/Kafka）；storage.list_runs_by_status 支持状态列表。test_worker_restart_recovery_runs_and_pending 验证 RUNNING+PENDING 双找回并重跑成功；test_worker_recover_pg_unavailable_does_not_block 验证 PG 不可用时 recover 返回 0 且 _recovered=False。
  (3) fq 重启恢复一致性 WORKER_FQ_RECOVERY_PASS：遗留在 RUNNING（覆盖 none/pre/qfq/post/hfq 五种）与 PENDING 的运行被恢复重跑后，真实执行 payload.fq / 落库 config.fq / 审计 snapshot.config.fq 全链路保持原 fq（非仅字段存在）；test_worker_restart_recovery_preserves_fq（5 值）与 test_worker_restart_recovery_pending_preserves_fq 验证；live 服务器提交 fq=pre 经完整链路 config.fq=snapshot.config.fq=pre。
  架构锁定：investment_data → InvestmentDataProvider → BulletTrade（create_backtest / 撮合 / 账户 / 订单 / 成交 / 指标 / 原生 HTML 报告）→ QuantRadar WebUI/API/Worker/history Run/Audit；禁止重实现 BulletTrade 回测/账户/订单/指标/报告能力。暂停：Qlib/ETF/因子研究/参数寻优/新模型/Agent/新交易引擎/新回测框架/任何无关新功能。）
```

---

## 当前 Blocked

```text
ETF                          BLOCKED（investment_data 无 ETF 表；Phase 11 前不建设）
alpha factor                 BLOCKED（investment_data 无因子表）
公司行为(分红/拆股)          PARTIAL（bao_a_stock_eod_info 真实 preclose/close；以除权缺口还原每股税前红利，引擎按 20% 预提税，NAV 与不复权一致；送转/派息无法从本表分离 -> PARTIAL；get_split_dividend 已实现）
ST 标记                      PARTIAL（bao_a_stock_eod_info.is_st ∈ {0,1}；get_extras('is_st'/'tradestatus') 已实现，df=True/Dict 两形态；bao 源仅至 2023-06-09）
Qlib 数据                     PASS（build_qlib_data 由 investment_data 真实导出；字段/复权口径与官方 investment_data 一致；mlruns 由 exp_manager 重定向临时目录不污染仓库）
停牌(tradestatus) 鲁棒性      PARTIAL（bao.tradestatus 列存在，语义与覆盖待 Phase 2 确认；bao 源至 2023-06-09）
InvestmentDataProvider       BASE IMPLEMENTED（Phase 2A）+ get_price PASS（Phase 2B）+ JQ 兼容核心 PASS（Phase 3）+ 真实 A 股回测 PASS（Phase 4）+ 真实复权 PASS（Phase 5）+ 公司行为/ST PASS（Phase 5 补全）
FastAPI / PostgreSQL / Worker / WebUI   PASS（PERSIST_WORKER_PASS + WEB_WORKBENCH_PASS 均已达成）
Qlib 最小闭环                 PASS（QLIB_BULLETTRADE_LOOP_PASS：Alpha158+LightGBM 端到端跑通并落地 BulletTrade 账户回测；高级研究/多模型/参数寻优属 Phase 10）
QMT / 实盘                    BLOCKED（未来实盘节点）
```

---

## 当前关键路径

```text
investment_data (Dolt 3307)
→ InvestmentDataProvider (Phase 1/2，实现 DataProvider ABC)
→ BulletTrade 回测 (Phase 4)
→ Snapshot / 可复现 (Phase 6)
→ Web 工作台 (Phase 7/8)
→ Qlib 最小闭环 (Closing 4)：investment_data → qlib_data → Alpha158+LGBModel → TopK Target Weight → BulletTrade 账户回测
→ Qlib 高级研究 (Phase 10，待办)
```

---

## 已验证事实（审计产物）

### 环境
- OS: Linux/Ubuntu（x86_64）；Python 3.12.3（目标 3.11 本机不可用，见风险）；Node v22.23.1。
- BulletTrade 基线：vendor/bullet-trade（BulletTrade v0.9.2，commit be0451b），无嵌套 .git。
- 安装：`pip install -e ./vendor/bullet-trade`；`import bullet_trade` → vendor/bullet-trade/bullet_trade/__init__.py。
- 附加：`pip install pyqlib==0.9.7`（仅验证 import）。

### investment_data（Dolt，14 表）
| 表 | 内容 | 规模 / 区间 |
|---|---|---|
| final_a_stock_eod_price | A 股日线主源（open/high/low/close/adjclose/volume/amount） | 18.3M 行；1990-12-19..2026-08-04；6129 标的；symbol 格式 `SH600601` |
| final_a_stock_limit | 涨跌停（pre_close/up_limit/down_limit） | 14.1M；1996-12-16..2023-06-12 |
| bao_a_stock_eod_info | 信息源（tradestatus 停牌 / is_st / adjfactor 复权因子 / adjclose / adjpreclose） | 14.3M；1990-12-19..2023-06-09；5183 标的 |
| ts_a_stock_eod_price | Tushare 日线源 | 18.0M |
| ts_a_stock_list | 证券主数据（ts_code `000001.SZ` / symbol `000001` / exchange / list_date / delist_date） | 5023 |
| ts_index_weight | 指数权重（index_code / stock_code `000001.SZ` / trade_date / weight） | 2.4M；6 指数；2005-04-08..2026-06-30 |
| ts_trade_day_calendar | 交易日历（exchange=SSE / date / is_open） | 13162；is_open=1 共 8797 日 |
| c_a_stock_eod_price / w_a_stock_eod_price / yahoo_a_stock_eod_price | 其他来源日线 | — |
| c_link_table / ts_link_table / yahoo_link_table | 跨源 symbol 映射（link_date / adj_ratio） | — |
| max_index_date | 指数最大日期（1 行） | — |

6 个指数：000300.SH、000852.SH、000905.SH、000906.SH、000985.SH、399300.SZ。

### Provider 机制（源码审计，回答 7 问）
1. **DataProvider ABC 接口**：`bullet_trade/data/providers/base.py`。抽象方法：`get_price`（含 `fq='pre'` 与 `pre_factor_ref_date`）、`get_trade_days`、`get_all_securities`、`get_index_stocks`、`get_split_dividend`；可选（默认抛 `NotImplementedError`）：`get_bars`、`get_ticks`、`get_index_weights`、`get_fundamentals`、`get_industry_stocks` 等。
2. **Provider 如何创建**：`bullet_trade/data/api.py:_create_provider(provider_name, overrides)` 工厂，按名称 import 并实例化具体类并注入配置；也可直接 `new` 实例传入 `set_data_provider`。
3. **是否已有外部注册机制**：**Phase 1 起为「是（通用注册表）」**。`providers/` 已有 jqdata/tushare/miniqmt/remote_qmt/rqdata/easy_tdx 实现；`_create_provider` 为硬编码 if 链（内置 Provider）。Phase 1 **新增 Generic Provider Registry**：`register_data_provider(name, factory, *, overwrite=False)` / `unregister_data_provider(name)`。注册后，`_create_provider` 会先查注册表，命中则用 `factory(merged_config)` 创建（统一入口、不复制逻辑）；未命中才走内置 if 链；未知名称仍 `ValueError`。
   - **不再**需要为外部 Provider（如未来的 `InvestmentDataProvider`）往 `_create_provider` 里加硬编码 `if target == "investment_data"` 分支；改为在 QuantRadar 侧用 `register_data_provider` 注册工厂，再 `set_data_provider(name)` 使用。
   - factory 契约：`factory(config: dict) -> DataProvider`（config = `get_data_provider_config()` 与 overrides 的合并）。
   - 内置 Provider 名称受保护，默认禁止外部覆盖（需显式 `overwrite=True`）。
   - 暴露位置：`bullet_trade.data.register_data_provider` / `unregister_data_provider`。
   - **生命周期（Phase 1.1）**：`register`（含 `overwrite=True`）会清除该名称既有 instance cache + auth state，使后续按名获取用（新）factory；`unregister` 清除 Registry/cache/auth 三者，但**不替换已激活的全局 `_provider`**；切换当前全局 Provider 必须显式 `set_data_provider(...)`。Registry 测试 13/13 通过。
   - **import 阶段初始化**：`bullet_trade.data.api` 在模块 import 时执行 `_provider = _create_provider()`（此时 Registry 为空，按 `DEFAULT_DATA_PROVIDER` 走内置 if 链）。因此 QuantRadar 必须在 import 之后、查询之前显式 `register_data_provider` + `set_data_provider`，不能依赖 `DEFAULT_DATA_PROVIDER=investment_data` 在 import 阶段自动注册（详见 03 的 Bootstrap 契约与配置边界）。
4. **set_data_provider 如何工作**：`api.set_data_provider(provider)` 接受实例或名称；实例直接存为全局 `_provider`，名称走 `_create_provider`；随后 `auth()`、绑定 sdk fallback、缓存、按需关闭 live 缓存。
5. **外层 get_price/history 如何调用 Provider**：`bullet_trade/data/api.py` 顶层 `get_price/history/get_trade_days` 直接调用全局 `_provider` 对应方法。
6. **BacktestEngine 如何取得 Provider**：`core/engine.py` import `get_data_provider`，回测中经 `get_data_provider()` 取全局 provider；并把 wrapped `set/get_data_provider` 注入策略命名空间，故策略内 `set_data_provider(...)` 即设置全局 provider。
7. **防未来数据机制**：(a) 结构性——引擎 `set_current_context(context)`，回测中 `get_price/history` 在 `end_date` 缺省时回退到 `_current_context.current_dt`（api.py ~1892-1915），只返回模拟“当前日”前数据；(b) 显式开关——`avoid_future_data=True` 时越界访问未来数据抛 `FutureDataError`（api.py ~1869）；复权锚点也用 `_current_context.current_dt`。

---

## 数据表映射（investment_data → Provider 方法）

```text
final_a_stock_eod_price      → get_price（原始价 + adjclose；symbol='SH600601'）
ts_trade_day_calendar        → get_trade_days（is_open=1 的 SSE 交易日）
ts_a_stock_list              → get_all_securities / get_security_info（上市/退市日期）
ts_index_weight              → get_index_weights + get_index_stocks（派生成分；stock_code='000001.SZ'）
final_a_stock_limit          → 涨跌停（可映射到 get_extras 或扩展方法）
bao_a_stock_eod_info         → is_st / tradestatus(停牌) / adjfactor(复权因子)
公司行为(分红/拆股)           → 无独立表；get_split_dividend 据 bao.preclose/close 除权缺口还原（PARTIAL：送转/派息未分离）
```

**symbol 格式不一致（关键）**：`final` 用 `SH600601`、`index/list` 用 `000001.SZ`、`list` 另有裸 `000001`。Provider 必须归一化；`c/ts/yahoo link_table` 含 `adj_ratio` 可辅助跨源对齐。

---

## 风险

```text
R1  Python 支持范围 >=3.11,<3.13（本机仅 3.12.3 可用，已验证安装/导入通过）。3.11 不可用、3.13 未验证；后续升级需复测。
R2  symbol 多格式：Provider 必须做归一化，否则指数/日线对不齐。
R3  investment_data 多源湖（final/c/ts/w/yahoo），final_* 似主源；Phase 2 需定主源与去重。
R4  复权：final 仅 adjclose，原始 factor 只在 bao(adjfactor)；引擎已有 dynamic pre-factor 逻辑，Provider 需供给 raw price + factor。
R5  公司行为显式数据缺失；ETF 缺失；alpha factor 缺失。
R6  Qlib 数据未构建（QLIB_DATA_NOT_BUILT）。
R7  trade calendar 仅 SSE 行（A 股日历统一，可接受）。
R8  vendor 为快照，无 upstream 完整 git 历史；禁止向 upstream 推送（见 02 第二节）。
```

---

## 下一任务

```text
Phase 1（已完成）：Generic Provider Registry —— CUSTOM_PROVIDER_REGISTRATION_PASS
Phase 1.1（已完成）：Registry 生命周期加固 —— PROVIDER_REGISTRY_LIFECYCLE_PASS
Phase 2A（已完成）：InvestmentDataProvider 基础能力 —— INVESTMENT_DATA_PROVIDER_BASE_PASS
Phase 2B（已完成）：原始日线 get_price(fq="none") —— 基于 final_a_stock_eod_price，日频，与数据库原表抽样对账 —— RAW_DAILY_PRICE_PASS
Phase 3（已完成）：JoinQuant 兼容核心 —— frequency/fq 别名归一、字段别名、history/attribute_history 经 Generic Provider Registry 接入 BulletTrade 引擎，与原表对账 —— JQ_COMPAT_CORE_PASS
Phase 4（已完成）：真实 A 股回测 —— InvestmentDataProvider 驱动 BacktestEngine 跑通端到端，验证数据链路/防未来数据/真实价对账 —— REAL_A_SHARE_BACKTEST_PASS
Phase 5（已完成）：真实复权 —— fq='pre'/'post'/'qfq'/'hfq' 基于 adjclose 与原始价真实因子，与原表对账 —— ADJUSTED_PRICE_PASS
Phase 6（已完成）：Snapshot / 可复现 —— 回测环境快照 + 结果指纹，同配置可复现 —— SNAPSHOT_REPRO_PASS
Phase 7（已完成）：FastAPI 服务基础 —— /api/price / /api/backtest / /api/snapshot 暴露真实能力 —— FASTAPI_CORE_PASS
Phase 8（已完成）：中文 WebUI + 浏览器策略回测 + 实验 + Web 构建（offline SPA）—— QUANTRADAR_STOCK_V1_PASS
主线闭环达成（QUANTRADAR_STOCK_V1_PASS）：investment_data → Provider → JoinQuant策略 → BulletTrade真实回测 → PIT → Snapshot → Deterministic → API → 中文Web → Experiment → 因子研究
Phase 9（进行中）：无基础设施部分已完成（因子研究 / Experiment / Makefile / Smoke / 浏览器策略回测 / 实验API / Web构建，QUANTRADAR_SMOKE_PASS + QUANTRADAR_STOCK_V1_PASS）；PostgreSQL + Worker 已完成（PERSIST_WORKER_PASS，连本机 1Panel 专用库 quantradar 验证异步回测落库）；正式 React WebUI 待 Item 3
Phase 10（下一）：Qlib 高级研究（Alpha158 / LightGBM 等，需 QLIB_DATA 构建，本地可行）
严谨研究型 V1 进行中（QUANTRADAR_RESEARCH_V1_WIP）：
  T1（已完成）：复权口径统一 + 同源验证 + 审计记录 fq（RESEARCH_T1_FQ_PASS；test_backtest_fq.py 3 passed）
  T2（已完成）：股票列表补全（RESEARCH_T2_UNIVERSE_PASS；extended_universe 从 final 补全 ts_a_stock_list 缺口 + 排除指数 + source='final_approx' PARTIAL；select_universe/run_qml_pipeline 增 use_extended；read_timeout 120s + query 断连重试；test_universe_extended.py 3 passed）
  T3（#60 已完成）：Qlib 多模型（lgb/xgb/mlp 探测可用性，本环境仅 lgb 可用、xgb/mlp 缺依赖抛 NotImplementedError 不伪造）+ grid_search_qlib（固定 seed 按 IC 选优、可复现）+ walk_forward_qlib（逐折不重叠防泄漏、可复现）；RESEARCH_T3_MULTIMODEL/GRID/WALKFORWARD/INIT_PASS；test_qlib_models/grid_search/walk_forward.py 共 8 passed
  T4（#62 已完成）：样本外稳健性验证 + 可复现报告；run_research_oos（grid 选优 + walk-forward 多折 OOS）→ 结构化报告（config/grid/folds/oos/environment），固定 seed 可复现；scripts/research_oos.py 端到端 CLI（复用/自动构建 qlib_data，产出 JSON+MD）；test_research_oos.py 2 passed（RESEARCH_T4_OOS_PASS）
  T5（#63 已完成）：conftest 确保研究测试带 requires_dolt（test_qlib_loop 补标记）+ QUANTRADAR_FORCE_NO_DOLT 模拟 CI；make research 端到端研究链路（reports/oos.json+md）；06_Qlib研究规范 第八节研究正确性规则；最终 make test 全量 + 模拟 CI 验收绿（RESEARCH_TEST_ISOLATION/MAKE_RESEARCH/SPEC_06_PASS）
BulletTrade WebUI 收口（#70~#74 已完成）：统一回测链 run_unified_backtest 复用 BulletTrade 原生报告管线（create_backtest→generate_report→generate_cli_report），产出 BulletTrade 原生 report.html/standard_report.html/metrics.json/CSV/PNG/日志/snapshot 于 runs/<run_id>/；修复 BulletTrade 明确 bug（create_backtest(benchmark=) 参数未接线致基准恒 0）；API 四端点（/async + /runs/{id} + /runs/{id}/report(full|standard) + /runs/{id}/artifacts）；ReportPage iframe 嵌入原生报告 + 审计面板 + 产物清单；验收 BULLETTRADE_WEB_REPORT_PASS（tests/unit/test_bullettrade_web_report.py 6 passed）
  WebUI 收口收尾（5 项达成）：
    ① CI 修绿：CI 无 Dolt/PG 时 backend（23 passed / 131 skipped）+ frontend 全绿；根因=3 个 Dolt 依赖测试缺 requires_dolt 标记 + 因子研究模块级 fixture setup 顺序 ERROR，已修（test_web_workbench 补标记 + test_factor_research universe fixture 加 try/except skip 守卫）。
    ② artifact 文件查看/下载：新增 GET /api/backtest/runs/{run_id}/artifacts/{name:path} 单文件端点（按扩展名推断 Content-Type + 防目录穿越），前端 ReportPage 产物清单链接到 getRunArtifactUrl（非报告产物可内联/下载，替代原先指向列表端点的死链）；test_async_backtest_runs_and_queryable 覆盖产物清单+单文件端点+穿越防护。
    ③ Worker 恢复 fq：worker._payload_from_record 从落库 config 还原 fq（none/pre/qfq/post/hfq），重启恢复（RUNNING→PENDING 重入队）不丢复权口径；全链 API submit(payload.fq)→config.fq→recover 重建→run_unified_backtest(_FQ_LOCK+use_real_price) 贯通；实跑验证 run config.fq=qfq、snapshot.config.fq=qfq。
    ④ 删除旧 ResultsView：frontend/src/components/ResultsView.tsx 已删除（无残留引用），报告图改为直接嵌入 BulletTrade report.html/standard_report.html（iframe）。
    ⑤ 浏览器实跑策略最终验收：启动后端+前端，经浏览器等价流程（提交真实策略 600519.XSHG + 基准 000300.XSHG + fq=qfq → 轮询 SUCCESS → 打开 BulletTrade 报告页 + 产物清单下载）跑通；实测 基准收益 4.19% / 累计超额收益 -2.47%，dolt_commit 入审计。
  外部待定（用户侧，不阻塞）：数据补齐方案（ST/停牌/列表，来自只读 Dolt，本仓库无法补齐）
禁止提前开发：PostgreSQL / ETF / QMT / 实盘 / Qlib 深化 / 因子 / 寻优（除非当前阶段需要或用户决策）
最终封版完成（BULLETTRADE_WEBUI_FINAL_PASS）：3 项必做——报告内联显示(REPORT_INLINE_PASS) / Worker 重启恢复双覆盖 RUNNING+PENDING(WORKER_RESTART_RECOVERY_PASS) / fq 重启恢复一致性(WORKER_FQ_RECOVERY_PASS)——全部达成，并已通过 live 服务器等价浏览器流程（提交 JoinQuant 兼容策略→轮询 SUCCESS→report?which=full|standard 均返回 Content-Disposition: inline→config.fq=snapshot.config.fq=pre 一致）最终验收。后端测试（Dolt+PG 13 passed）+ CI 后端（无 Dolt/PG 24 passed/138 skipped）+ 前端构建（npm run build 成功）全绿。
下一动作：BulletTrade WebUI 主线已封版（BULLETTRADE_WEBUI_FINAL_PASS）。架构锁定于 investment_data → InvestmentDataProvider → BulletTrade 原生回测/账户/订单/指标/HTML 报告 → QuantRadar WebUI/API/Worker/Run/Audit。停止一切扩张，等待用户决策下一阶段（Qlib/ETF/模型/寻优/新交易引擎/新回测框架等新功能仍暂停）。
```
