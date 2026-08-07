# QuantRadar 当前开发任务

文件：`docs/ACTIVE_PHASE.md`

**当前阶段：主线闭环已达成（QUANTRADAR_STOCK_V1_PASS）；下一阶段 Phase 10 Qlib 或 Phase 9 Postgres/Worker（待环境）**

```text
主线验收 QUANTRADAR_STOCK_V1_PASS 已达成：
  - investment_data → Provider → JoinQuant策略(/api/backtest/strategy 用户源码) → BulletTrade真实回测
    → PIT → Snapshot/Deterministic → API → 中文Web(frontend/dist 离线 SPA) → Experiment → 因子研究
  - QUANTRADAR_SMOKE_PASS 全链路通过（含浏览器策略回测 + Web 构建）
Phase 8 补全（STOCK_V1 关键缺口）：
  - /api/backtest/strategy 接受 JoinQuant 兼容用户源码，引擎注入 get_price/order_target/log/g/run_daily，
    复用 BulletTrade 撮合/账户/订单/成交/调度，不重实现
  - /api/experiments（列表/加载/保存）复用 backend/quantradar/experiment
  - frontend/dist/index.html：离线自包含中文 SPA（行情/策略回测/实验），GET / 优先托管，满足「Web build 成功」
Phase 5 公司行为/ST 已补全（CORPORATE_ACTION_ST_PASS）；Phase 9 无基础设施部分已完成（QUANTRADAR_SMOKE_PASS）
React+TS+Vite 源码脚手架 PARTIAL：frontend/ 标准 Vite 工程就位，构建需 npm install，本环境 TLS 阻断 npm registry；
  联网后 cd frontend && npm install && npm run build 可生成 Vite 版 dist 覆盖离线 SPA
剩余 Phase 9（PostgreSQL / Worker）仍需环境前提（见下方「环境前提」），就绪前不自动写入未知库。
Phase 10 Qlib（Alpha158 / LightGBM，需本地 QLIB_DATA 构建）为下一可行主线扩展。
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
