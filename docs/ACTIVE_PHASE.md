# QuantRadar 当前开发任务

文件：`docs/ACTIVE_PHASE.md`

**当前阶段：Phase 3 — JoinQuant 兼容层（JQ Compat Core）**

```text
上一阶段 Phase 2B 已完成（RAW_DAILY_PRICE_PASS）：
  - get_price(fq='none') 日频原始价（final_a_stock_eod_price）
  - 单/多证券 panel（MultiIndex 字段,证券）、start/end/count/fields、与原表抽样对账一致
  - fq!=none / frequency!=daily 明确 NotImplementedError；上市前/退市后/无数据窗口显式空不伪造
  - 新增 17 个测试；QuantRadar 测试 55/55 通过；BulletTrade registry 回归 13/13 通过
本阶段做 Phase 3；完成后自动进入 Phase 4（无人值守）。
```

---

# 一、目标

在 InvestmentDataProvider 已有能力之上，补齐 **JoinQuant 兼容语义**，使上层 BulletTrade
回测引擎（Phase 4）能无感调用 `get_price` / `history` / `attribute_history` 等接口，
且结果符合 JQ 约定。

```text
禁止 mock；禁止返回虚假数据；复权（fq='pre'/'post'）若需实现须基于真实因子，属本阶段但可限范围。
```

---

# 二、范围与边界（强制）

```text
允许：
  - 对齐 BulletTrade 顶层 get_price / history 调用约定（频率、复权、panel、skip_paused/fill_paused）
  - get_price 支持 frequency 别名（'d'/'day'/'daily' 归一为 daily）；其余仍 NotImplementedError
  - 复权价（fq='pre'/'post'）读取真实复权因子（final/bao 表的 adjclose/adjfactor）实现；
    若因子源不可用则明确 PARTIAL/LIMIT，绝不伪造
  - attribute_history / history 基于 get_price 的组合封装（字段名映射：open/high/low/close/volume/amount）
  - 停牌/涨跌停语义与 JQ 对齐（get_price 已显式 PARTIAL；涨跌停数据来自 final_a_stock_limit）
  - 补齐 tests/unit 测试

禁止：
  - 改动 BulletTrade 核心（registry / engine）
  - 写入 investment_data
  - 扩大至 ETF / QMT / 实盘
  - 提前进入 FastAPI / WebUI / Qlib
```

---

# 三、兼容契约

```text
1. get_price(fq='none')：沿用 Phase 2B 实现；本阶段仅扩展 fq 别名与频率别名归一。
2. get_price(fq='pre'/'post')：使用真实复权因子调整 close/开盘等；或返回 adjclose 直读（若源为后复权）。
   必须与原表 adjclose 对账一致；不复权时绝不混入 adjclose（已验证）。
3. history / attribute_history：封装 get_price，按 JQ 字段名（'open'/'close'/...、'money'->amount）
   返回，保证 BulletTrade 回测调用签名兼容。
4. Panel 形状：多证券 MultiIndex(字段, 证券)；单证券扁平 columns（与 Phase 2B 一致）。
```

---

# 四、测试

至少覆盖：

```text
- frequency 别名（'d'/'day'）归一为 daily 可调用
- fq='pre'/'post' 复权值与原表 adjclose 对账（或显式 PARTIAL 若因子不可用）
- history / attribute_history 封装返回字段与形状正确
- 不复权时绝不混入 adjclose（回归）
- 上市前/退市后/无数据窗口 显式空（回归）
- BulletTrade registry 回归保持全过
```

运行：

```text
tests/unit （pytest）
BulletTrade registry 回归（test_provider_registry.py）保持全过
```

---

# 五、验收

完成标志：`JQ_COMPAT_CORE_PASS`

```text
[PASS] frequency / fq 别名归一
[PASS] 复权价（如需）与原表 adjclose 对账一致 / 或明确 PARTIAL
[PASS] history / attribute_history 封装兼容 JQ 字段与形状
[PASS] 不复权绝不混入 adjclose（回归）
[PASS] QuantRadar 新增测试通过 + BulletTrade registry 回归通过
[PASS] 单一 commit 含 JQ_COMPAT_CORE_PASS
```

---

# 六、结束条件

```text
1. 实现 JQ 兼容封装 + 复权（按需）+ 对账测试
2. 更新 docs/CURRENT_STATE.md（Provider 状态、JQ 兼容 PASS）
3. git diff --check 无遗留空白错误
4. 单一 commit（JQ_COMPAT_CORE_PASS）
5. push origin main
6. 将 ACTIVE_PHASE 改为 Phase 4 → 自动进入 Phase 4（真实 A 股回测）
```
