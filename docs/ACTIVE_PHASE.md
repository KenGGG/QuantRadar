# QuantRadar 当前开发任务

文件：`docs/ACTIVE_PHASE.md`

**当前阶段：Closing Phase — 收尾补齐 4 项（Audit → PostgreSQL/Worker → React WebUI → Qlib）→ QUANTRADAR_V1_PASS**

```text
目标：在已达成 QUANTRADAR_STOCK_V1_PASS 的主线之上，补齐 4 项并标记 QUANTRADAR_V1_PASS。
执行顺序（每项：开发→测试→修复→更新 CURRENT_STATE→commit→push→下一项）：
  1) 完整 Snapshot/Audit          PASS  FULL_AUDIT_REPRO_PASS ✅
     - build_snapshot 补齐 snapshot_id/config_hash/strategy_hash/result_hash/metrics/environment
       （dolt_commit, schema_hash, provider_version, bullettrade_commit, quantradar_commit）
     - backend/quantradar/audit.py 采集 Dolt HEAD 与数据表 schema 哈希
     - 确定性测试：NAV/Trades/Positions/Metrics 一致 + 审计指纹一致
  2) PostgreSQL + Worker          PASS  PERSIST_WORKER_PASS ✅
     - 模型：Strategy / BacktestRun / Experiment / Snapshot / Metrics（SQLAlchemy，storage.py）
     - 异步：提交回测 → run_id → Worker 后台线程执行 run_backtest(BulletTrade) → PostgreSQL 保存 → API 查状态/结果
     - 本机 1Panel Postgres 专用库 quantradar 已建表并验证真实回测落库（4/4 集成测试通过，不触碰既有库）
     - API：POST /api/backtest/async + GET /api/backtest/runs/{id} + GET /api/backtest/runs
  3) 正式 React WebUI             待办 WEB_WORKBENCH_PASS
     - React+TS+Vite+AntD+Monaco+ECharts；策略编辑/回测提交/运行状态/收益NAV回撤图/Metrics/Positions/Trades/Logs/数据状态/Experiment比较
     - npm registry 现已可达，可 npm install 构建（取代手写 frontend/dist）
  4) Qlib 最小闭环                待办 QLIB_BULLETTRADE_LOOP_PASS
     - Alpha158 + LightGBM：Train/Valid/Test/Prediction/IC/RankIC/TopK/Target Weight
     - investment_data → Qlib → Prediction → Target Weight → BulletTrade → Account Backtest
终验：FULL_AUDIT_REPRO_PASS + PERSIST_WORKER_PASS + WEB_WORKBENCH_PASS + QLIB_BULLETTRADE_LOOP_PASS + QUANTRADAR_SMOKE_PASS 全绿 → QUANTRADAR_V1_PASS
```

---

# 一、目标

把回测结果与快照**持久化到 PostgreSQL**，并引入**Worker** 做异步回测（提交即返回
run_id，后台执行后写回结果）。与 Phase 6/7/8 的 API/WebUI 衔接，形成可审计的研究闭环。

```text
数据正确性 > 可复现性 > 持久化 > 异步。禁止向未知/未授权数据库写入（必须停止条件）。
```

---

# 二、环境前提（Phase 9 启动前必须就位）

```text
- PostgreSQL 实例可达（当前 127.0.0.1:5432 端口已开，但缺少已知凭证/库名）。
- .venv 安装 Postgres 驱动（psycopg2-binary / psycopg）与连接串配置
  （QUANT_RADAR_PG_URL，含库名/用户/密码）。
- 凭证仅来自环境变量；禁止在代码或提交中硬编码密码。
```

> 注意：本阶段**不**自动连接或写入未知数据库（属「不可逆/未授权 DB 写」必须停止条件）。
> 环境未就绪时，Phase 9 不得执行，应暂停等待凭证/库名就绪。

---

# 三、范围与边界（强制，环境就绪后）

```text
允许：
  - quantradar/storage.py（SQLAlchemy）：建表（backtest_runs / snapshots）、
    save_backtest_run / get_backtest_run / save_snapshot / get_snapshot。
  - quantradar/worker.py：BacktestWorker.submit(payload) -> run_id，后台线程/进程执行
    真实回测（复用 Phase 4/7 逻辑）并写回 Postgres；提供 get_status(run_id)。
  - API 扩展：POST /api/backtest/async（返回 run_id）、GET /api/backtest/runs/{id}。
  - 补齐 tests/unit/test_storage.py（用临时/测试库，或跳过若无可用 Postgres）。

禁止：
  - 改动 BulletTrade 核心。
  - 向未知的 investment_data 或任意生产库写入。
  - 提前进入 Qlib / ETF / QMT / 实盘。
```

---

# 四、测试

```text
- 环境就绪时：回测结果写入 Postgres 后可按 run_id 取回，与 Snapshot 指纹一致。
- Worker 异步提交 -> 轮询/等待 -> 结果持久化。
- 无可用 Postgres 时：相关测试 skip（不阻塞套件），其余全量 + registry 回归保持全过。
```

---

# 五、验收（环境就绪后）

完成标志：`PERSIST_WORKER_PASS`

```text
[PASS] 回测结果与快照持久化到 PostgreSQL 并可按 id 取回
[PASS] Worker 异步执行真实回测并写回结果
[PASS] API 暴露异步提交/查询接口
[PASS] 补充测试并全过（无 Postgres 时 skip）；registry 回归 + 全量测试保持全过
[PASS] 单一 commit 含 PERSIST_WORKER_PASS
```

---

# 六、结束条件

```text
1. 实现 PostgreSQL 持久化 + Worker + API 扩展 + 测试（环境就绪）
2. 更新 docs/CURRENT_STATE.md（持久化 / Worker PASS）
3. git diff --check 无遗留空白错误
4. 单一 commit（PERSIST_WORKER_PASS）
5. push origin main
6. 将 ACTIVE_PHASE 改为 Phase 10（Qlib 高级研究，按需）-> 自动进入 Phase 10
```
