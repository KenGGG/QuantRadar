# QuantRadar 当前开发任务

文件：`docs/ACTIVE_PHASE.md`

**当前阶段：Hardening 完成（FUNCTIONAL_V1_PASS）→ 严谨研究型 V1 进行中（RESEARCH_V1_WIP，T1/T2/T3 已完成）**

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
- 数据层 PARTIAL：investment_data 的 bao 源（ST/停牌/复权因子）仅至 2023-06-09；
  2023 后数据（指数权重至 2026-06-30，日线至 2026-08-04）部分残缺，严谨研究需补齐。
- 回测腿与 Qlib 训练复权口径【实测已统一，旧认知纠正】：final_a_stock_eod_price.close 本身已是
  连续复权价（除权缺口已消除），故回测腿（读 final.close，fq='none'）与 Qlib 训练（读 final.adjclose
  后复权）天生同源，日收益率完全一致、无除权假跳变。T1 已把 fq 配置化（run_backtest/
  run_target_weight_backtest 支持 none/pre/qfq/post/hfq）+ 审计记录 fq；默认 fq='none' 保持兼容。
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

# 六、严谨研究型 V1 子项（进行中）

## T1) 复权口径统一 + 同源验证 + 审计记录 fq —— RESEARCH_T1_FQ_PASS ✅
- `snapshot.py`：`build_snapshot` 增 `fq` 参数，写入 config（位于 benchmark 之后、seed 之前）。
- `backtest.py`：`run_backtest` 增 `fq: str = "none"`（可选 none/pre/qfq/post/hfq）；`_FQ_LOCK`
  线程安全切换 BulletTrade `use_real_price`（`_use_real_price = _fq != "none"`），整个回测体包在
  `with _FQ_LOCK: set_option("use_real_price", _use_real_price) ... finally: 还原`；两路径均透传 `fq`。
- `qml/bridge.py`：`run_target_weight_backtest` 默认 `fq="pre"` 并透传 `run_backtest(..., fq=fq)`
  （pre 与 Qlib 的 hfq 在同一窗口收益率等价，仅净值绝对水平缩放常数因子）。
- 实测纠正：final.close 已是连续复权价，回测腿与 Qlib 训练同源，无除权假跳变（旧认知不实）。
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

## T4) 样本外稳健性验证 + 可复现报告 —— #62 待做
- `scripts/research_oos.py`：端到端跑 T3 的 walk-forward，输出样本外指标 + 可复现报告（JSON+MD）。
- `tests/unit/test_research_oos.py`：验证报告字段齐全、可复现（同输入同输出）。

## T5) 测试隔离 / CI / smoke 扩展 + 文档 —— #63 待做
- `conftest` 确保新增测试带 `requires_dolt`；`make smoke` 扩展覆盖研究链路。
- 文档：`ACTIVE_PHASE.md` / `CURRENT_STATE.md` 升 `QUANTRADAR_RESEARCH_V1_WIP`；更新 `06_Qlib研究规范.md`。
- 最终 `make test` + 模拟 CI 验收。

```text
外部待定（用户侧，不阻塞）：数据补齐方案（ST/停牌/列表，来自只读 Dolt，本仓库无法补齐）。
元信息缺口：bao_a_stock_eod_info→2023-06-09；final_a_stock_limit→2023-06-12；ts_a_stock_list→2022-07-18。
价格+adjclose→2026-08-04；指数权重→2026-06-30（完整）。
```
