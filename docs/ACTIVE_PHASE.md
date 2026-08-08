# QuantRadar 当前开发任务

文件：`docs/ACTIVE_PHASE.md`

**当前阶段：Hardening & Research Correctness —— 已完成（降级为 FUNCTIONAL_V1_PASS）**

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
- 回测腿使用原始价（get_price fq='none'），与 Qlib 训练用的后复权价口径不完全一致；
  严格净值归因需统一复权口径。
- Qlib 仅最小闭环（Alpha158+LightGBM）；多模型/参数寻优/更严谨的样本外评估属后续研究。
- 单 uvicorn 进程模型；多进程水平扩展（分布式锁 FOR UPDATE SKIP LOCKED）不在本地工具范围。
```

---

# 五、下一阶段（未启动，需另行确认）

```text
「严谨研究型 V1」：在 FUNCTIONAL_V1 之上，补齐数据层完整性、统一复权口径、扩展 Qlib 研究，
并对关键结论做样本外稳健性验证。启动前需明确范围与数据补齐方案，不自动进入。
```
