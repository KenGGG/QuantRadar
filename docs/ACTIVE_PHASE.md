# QuantRadar 当前开发任务

文件：`docs/ACTIVE_PHASE.md`

**当前阶段：Phase 5 — 复权（基于真实因子的前/后复权）**

```text
上一阶段 Phase 4 已完成（REAL_A_SHARE_BACKTEST_PASS）：
  - InvestmentDataProvider 驱动 BacktestEngine 跑通真实 A 股回测（600519.XSHG，2023Q1）
  - 引擎 get_trade_days/get_security_info/get_price/current_data 全部由 Provider 承接
  - 防未来数据生效；资产曲线来自真实价且与原表对账一致
  - get_price 扩展 high_limit/low_limit（final_a_stock_limit）/paused（volume==0 派生）
本阶段做 Phase 5（复权）；完成后自动进入 Phase 6（Snapshot / 可复现）。
```

---

# 一、目标

把 `get_price` 的 `fq='pre'/'post'/'qfq'/'hfq'`（及 `pre-forward`/`post-forward`）从
Phase 3/4 的「原始价 LIMIT 透传」升级为**基于真实复权因子的前/后复权**，且与原表
`final_a_stock_eod_price.adjclose` 抽样对账一致。绝不伪造因子。

```text
禁止 mock；禁止编造复权因子；复权必须可追溯到 adjclose 与原始价的数值关系。
数据正确性 > 防未来数据 > 复现性 > 回测指标。
```

---

# 二、范围与边界（强制）

```text
允许：
  - fq='post'/'hfq'/'post-forward'：返回后复权价。final_a_stock_eod_price.adjclose 即源后复权
    收盘价；通过因子 F_t = adjclose_t / raw_close_t 反推 open/high/low 的后复权价，close 须
    精确等于 adjclose_t（对账基准）。
  - fq='pre'/'qfq'/'pre-forward'：前复权（以 pre_factor_ref_date 为基准日；缺省取窗口末日/
    当前回测日）。qfq_t = raw_t * (F_t / F_R)，其中 F_R = adjclose_R / raw_close_R；
    基准日 t=R 时 qfq_R == raw_R（对账基准），绝不偏离原始价。
  - 仅对 OHLC（open/high/low/close）做复权缩放；volume/amount/money 保持原始成交量与成交额
    （与 JoinQuant 约定一致，不伪造）。
  - 复用 get_price 既有字段别名 / frequency 别名 / 防未来数据 / 边界守卫。
  - 补齐 tests/unit 对账测试（post == adjclose；pre 在基准日 == raw；与原表抽样一致）。

禁止：
  - 改动 BulletTrade 核心（registry / engine / api）。
  - 写入 investment_data；编造不存在的因子。
  - 提前进入 FastAPI / WebUI / Qlib / ETF / QMT / 实盘。
```

---

# 三、复权契约（数值关系，须被测试覆盖）

```text
设 raw_t = (open/high/low/close)_t 原始价，adj_t = adjclose_t（源后复权收盘价）。
因子 F_t = adj_t / raw_close_t  （raw_close_t==0 时 F_t=1.0，避免除零）。
- 后复权 hfq_t(field) = raw_t(field) * F_t        （close 须 == adj_t）
- 前复权 qfq_t(field) = raw_t(field) * (F_t / F_R)，F_R = adj_R / raw_close_R
  基准日 R（pre_factor_ref_date；缺省=窗口末日/当前回测日）→ qfq_R == raw_R
volume/amount 不参与缩放（原始成交）。
```

---

# 四、测试

至少覆盖：

```text
- fq='post' 的 close 精确等于原表 adjclose（抽样多日）。
- fq='pre' 在基准日（pre_factor_ref_date）的 close 精确等于原始 close。
- fq='post'/'pre' 与原表抽样对账（open/high/low 经因子缩放一致）。
- fq='none' 行为不变（仍为原始价，绝不混入 adjclose）。
- volume/amount 在 fq='pre'/'post' 下保持原始值（不变造）。
- 防未来数据：fq='pre' 仍受 end_date/current_dt 约束。
- BulletTrade registry 回归 + QuantRadar 全量测试保持全过。
```

运行：

```text
tests/unit （pytest）
vendor/bullet-trade/tests/unit/test_provider_registry.py （回归）
```

---

# 五、验收

完成标志：`ADJUSTED_PRICE_PASS`

```text
[PASS] fq='post'/'hfq' 返回后复权价，close 精确等于原表 adjclose
[PASS] fq='pre'/'qfq' 返回前复权价，基准日 close 精确等于原始 close
[PASS] 复权因子可追溯到 adjclose 与原始价，无编造
[PASS] volume/amount 在复权下保持原始值
[PASS] 补充 tests/unit 对账测试并全过；registry 回归 + 全量测试保持全过
[PASS] 单一 commit 含 ADJUSTED_PRICE_PASS
```

---

# 六、结束条件

```text
1. 实现 fq='pre'/'post'/'qfq'/'hfq' 真实复权（基于 adjclose 与原始价因子）+ 对账测试
2. 更新 docs/CURRENT_STATE.md（Provider 复权 PASS）
3. git diff --check 无遗留空白错误
4. 单一 commit（ADJUSTED_PRICE_PASS）
5. push origin main
6. 将 ACTIVE_PHASE 改为 Phase 6（Snapshot / 可复现）-> 自动进入 Phase 6
```
