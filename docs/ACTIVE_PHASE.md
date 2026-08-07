# QuantRadar 当前开发任务

文件：`docs/ACTIVE_PHASE.md`

**当前阶段：Phase 6 — Snapshot / 可复现（回测环境与结果固化）**

```text
上一阶段 Phase 5 已完成（ADJUSTED_PRICE_PASS）：
  - get_price 真实复权（fq='pre'/'post'/'qfq'/'hfq'），因子由 adjclose 与原始价推导，绝不伪造
  - 后复权 close 精确等于原表 adjclose；前复权基准日 close 精确等于原始 close
  - 仅缩放 OHLC，volume/amount 保持原始；Phase 4 回测在 fq='pre' 下行为不变
本阶段做 Phase 6（Snapshot / 可复现）；完成后自动进入 Phase 7（FastAPI / WebUI 基础）。
```

---

# 一、目标

让真实 A 股回测**可复现**：同一份策略 + 同一份数据 + 同一份配置，多次运行得到逐日一致的
结果，并能把「运行环境快照」固化到磁盘以便复盘与审计。

```text
数据正确性 > 可复现性 > 回测指标。禁止编造指纹；指纹必须来自真实运行产物。
```

---

# 二、范围与边界（强制）

```text
允许：
  - 新增 quantradar.snapshot：捕获一次回测运行的「环境快照」与「结果指纹」
      * 环境：provider 名称、investment_data 连接指纹（host/db，不存密码）、
        数据 as-of（覆盖区间最大交易日 / 快照版本号）、策略参数(extras)、
        initial_cash、start/end、frequency、随机种子（若有）。
      * 结果指纹：daily_records 的确定性哈希（经四舍五入后序列化），用于复现校验。
  - 提供 save_snapshot / load_snapshot（JSON），可_round_trip。
  - 复现校验：同一配置两次运行，daily_records 完全一致（确定性测试）。
  - 补齐 tests/unit/test_snapshot.py。

禁止：
  - 改动 BulletTrade 核心（registry / engine / api）。
  - 写入 investment_data。
  - 提前进入 FastAPI / WebUI / Qlib / ETF / QMT / 实盘（除非本阶段需要）。
```

---

# 三、兼容契约

```text
- Snapshot 是 QuantRadar 层能力，包裹既有 BacktestEngine 运行结果，不改变引擎行为。
- 数据指纹仅作「复现凭证」，不参与价格计算；价格仍来自 InvestmentDataProvider（实时查询）。
- 若 investment_data 数据更新（区间扩展 / 复权因子修正），指纹应随之变化 -> 视为新快照。
```

---

# 四、测试

至少覆盖：

```text
- 同一策略 + 同一配置连续两次运行，daily_records 逐日一致（可复现性核心断言）。
- save_snapshot -> load_snapshot round-trip：环境字段与结果指纹完整还原。
- 结果指纹对数据/配置变化敏感（改 initial_cash 或区间 -> 指纹不同）。
- QuantRadar 全量测试 + BulletTrade registry 回归保持全过。
```

运行：

```text
tests/unit （pytest）
vendor/bullet-trade/tests/unit/test_provider_registry.py （回归）
```

---

# 五、验收

完成标志：`SNAPSHOT_REPRO_PASS`

```text
[PASS] 同配置两次运行 daily_records 逐日一致（确定性）
[PASS] Snapshot 可 save/load round-trip，环境 + 结果指纹完整
[PASS] 指纹对配置/数据变化敏感
[PASS] 补充 tests/unit/test_snapshot.py 并全过；registry 回归 + 全量测试保持全过
[PASS] 单一 commit 含 SNAPSHOT_REPRO_PASS
```

---

# 六、结束条件

```text
1. 实现 Snapshot（环境快照 + 结果指纹）+ 复现校验测试
2. 更新 docs/CURRENT_STATE.md（Snapshot / 可复现 PASS）
3. git diff --check 无遗留空白错误
4. 单一 commit（SNAPSHOT_REPRO_PASS）
5. push origin main
6. 将 ACTIVE_PHASE 改为 Phase 7（FastAPI / WebUI 基础）-> 自动进入 Phase 7
```
