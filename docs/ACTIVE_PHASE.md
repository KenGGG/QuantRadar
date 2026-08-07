# QuantRadar 当前开发任务

文件：`docs/ACTIVE_PHASE.md`

**当前阶段：Phase 7 — FastAPI 服务基础（Provider / Backtest / Snapshot 接口）**

```text
上一阶段 Phase 6 已完成（SNAPSHOT_REPRO_PASS）：
  - quantradar.snapshot 固化回测环境与 daily_records 结果指纹，可 save/load
  - 同配置两次运行逐日一致（可复现性核心断言）；指纹对配置变化敏感
本阶段做 Phase 7（FastAPI 服务基础）；完成后自动进入 Phase 8（PostgreSQL / Worker，按需）。
```

---

# 一、目标

把已验证的 QuantRadar 能力（InvestmentDataProvider / 真实回测 / Snapshot）通过
**FastAPI** 暴露为 HTTP 接口，供中文 WebUI 与 Experiment 调用。本阶段只建「服务骨架 +
核心只读/回测接口」，不含 PostgreSQL / Worker / 鉴权（Phase 8 起）。

```text
数据正确性 > API。所有接口仅透传真实 investment_data；禁止 mock、禁止编造。
```

---

# 二、范围与边界（强制）

```text
允许：
  - backend/quantradar/api/app.py：FastAPI 应用
      * GET  /api/health                      健康检查（返回 provider 状态）
      * GET  /api/price                        透传 provider.get_price
            （security/start/end/fq/fields 参数；返回 JSON 行情）
      * POST /api/backtest                     运行真实回测，返回
            {summary, snapshot(环境+结果指纹)}；内部复用 BacktestEngine + Snapshot
      * POST /api/snapshot/save  + GET /api/snapshot/load
            快照持久化（JSON 文件，可配置目录）
  - 依赖量化：fastapi / uvicorn / httpx（TestClient 用）；仅在 .venv 内安装。
  - 补齐 tests/unit/test_api.py（用 fastapi.testclient，无需起真实服务）。

禁止：
  - 改动 BulletTrade 核心。
  - 写入 investment_data。
  - 引入 PostgreSQL / Worker / 鉴权（Phase 8）。
  - 提前进入 Qlib / ETF / QMT / 实盘。
```

---

# 三、兼容契约

```text
- 接口返回结构稳定（version 字段）；价格字段名沿用 JoinQuant（open/high/low/close/
  volume/amount/money），fq 语义与 provider.get_price 一致。
- backtest 接口内部 bootstrap_investment_data(set_active=True) 确保读真实数据；
  返回 fingerprint 与原 test_snapshot 计算方式一致（可复现）。
```

---

# 四、测试

至少覆盖：

```text
- /api/health 返回 200 且 provider 状态正常
- /api/price 返回与 provider.get_price 一致的真实行情（抽样对账）
- /api/backtest 运行真实回测，返回 summary + fingerprint（可复现：两次相同请求指纹一致）
- /api/snapshot save/load round-trip
- QuantRadar 全量测试 + BulletTrade registry 回归保持全过
```

运行：

```text
tests/unit （pytest）
vendor/bullet-trade/tests/unit/test_provider_registry.py （回归）
```

---

# 五、验收

完成标志：`FASTAPI_CORE_PASS`

```text
[PASS] FastAPI 应用可 import 与 TestClient 启动
[PASS] /api/price 透传真实行情并可对账
[PASS] /api/backtest 运行真实回测并返回可复现 fingerprint
[PASS] /api/snapshot save/load round-trip
[PASS] 补充 tests/unit/test_api.py 并全过；registry 回归 + 全量测试保持全过
[PASS] 单一 commit 含 FASTAPI_CORE_PASS
```

---

# 六、结束条件

```text
1. 实现 FastAPI 服务骨架 + 核心接口 + 测试
2. 更新 docs/CURRENT_STATE.md（FastAPI 服务 PASS）
3. git diff --check 无遗留空白错误
4. 单一 commit（FASTAPI_CORE_PASS）
5. push origin main
6. 将 ACTIVE_PHASE 改为 Phase 8（PostgreSQL / Worker，按需）-> 自动进入 Phase 8
```
