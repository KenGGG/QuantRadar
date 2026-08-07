# QuantRadar 当前开发任务

文件：`docs/ACTIVE_PHASE.md`

**当前阶段：Phase 4 — 真实 A 股回测（端到端数据链路 + 防未来数据）**

```text
上一阶段 Phase 3 已完成（JQ_COMPAT_CORE_PASS）：
  - frequency 别名 d/day/1d -> daily；字段别名 money -> amount
  - fq='none' 原始价 + fq='pre'/'post' 等价原始价 LIMIT 透传（绝不伪造复权）
  - get_price / history / attribute_history 经 Generic Provider Registry 接入 BulletTrade 引擎
  - 与原表抽样对账一致，close != adjclose 已验证；13 个 JQ 兼容测试通过
本阶段做 Phase 4；完成后自动进入 Phase 5（复权）。
```

---

# 一、目标

用 **InvestmentDataProvider**（Phase 2A/2B/3 已落地）驱动 BulletTrade
**BacktestEngine** 跑通一段真实 A 股回测，从端到端验证：

1. 回测引擎经 Generic Provider Registry 读到 investment_data 真实行情；
2. 引擎内部的价格 / 交易日历 / 标的元数据调用全部被 Provider 正确承接；
3. 防未来数据机制生效——策略 `handle_data` 只能看到「当前交易日」及之前的数据；
4. 回测产出的资产曲线 / 成交来自真实价格，且可与原表抽样对账。

```text
禁止 mock；禁止伪造价格 / 复权；禁止写 investment_data；禁止改 BulletTrade 核心。
数据正确性 > 防未来数据 > 复现性 > 回测指标本身。
```

---

# 二、范围与边界（强制）

```text
允许：
  - 编写最小但真实的策略（initialize + handle_data），买入并持有一只真实 A 股
    （如 600519.XSHG），并在 handle_data 内调用 get_price / history 验证数据可得。
  - bootstrap_investment_data(set_active=True) 后构造 BacktestEngine 并 run()。
  - 对回测结果断言：
      * 引擎无异常跑完（数据链路打通）；
      * daily_records / 资产曲线非空，且数值来自真实价格（>0、与原表抽样对账一致）；
      * 防未来数据：在 handle_data 内断言 get_price(end_date 缺省) 最大日期 <= current_dt；
        或开启 avoid_future_data 并确认无 FutureDataError。
  - 补齐 tests/unit/test_real_backtest.py。
  - 若引擎需要，可扩展 Provider 承接更多字段（如 paused 由 volume==0 派生，PARTIAL 标注），
    但不得伪造；属本阶段可选增强。

禁止：
  - 改动 BulletTrade 核心（engine / registry / api）。
  - 写入 investment_data。
  - 引入 mock 数据源或回放假数据。
  - 提前进入复权（Phase 5）/ FastAPI / WebUI / Qlib / ETF / QMT / 实盘。
```

---

# 三、兼容契约（引擎对 Provider 的依赖，已审计）

```text
引擎回测中会调用以下 Provider 方法（均已在 Phase 2A/2B/3 实现）：
  - provider.get_trade_days(start_date, end_date)        -> 交易日历（SSE）
  - get_security_info(security)                           -> 元数据 dict（含 type）
  - api.get_price(security, end_date=current_dt,
                  frequency='daily', fields=['open'/'close'], count=1, fq=fq_mode)
        fq_mode = 'pre' if use_real_price else 'none'（默认 none，Provider 已支持）
  - provider.get_price(fields=['volume','paused'], fq='none')  -> 停牌检测（paused 暂不支持，
        由引擎 try/except 降级为「非停牌」，标记 PARTIAL；可后续增强）
  - get_split_dividend：引擎加载公司行为时调用，失败即降级为空列表（Phase 5 前 NOT IMPLEMENTED，安全）
```

---

# 四、测试

至少覆盖：

```text
- BacktestEngine 用 InvestmentDataProvider 跑完一段真实区间（如 2023-01-01..2023-03-31）无异常。
- 回测产出的每日资产 / 持仓非空，且价格可与原表 final_a_stock_eod_price 抽样对账一致。
- 防未来数据：策略内 get_price（不传 end_date）最大返回日 <= context.current_dt。
- BulletTrade registry 回归（test_provider_registry.py）保持全过。
- QuantRadar 全量测试（tests/unit）保持全过。
```

运行：

```text
tests/unit （pytest）
vendor/bullet-trade/tests/unit/test_provider_registry.py （回归）
```

---

# 五、验收

完成标志：`REAL_A_SHARE_BACKTEST_PASS`

```text
[PASS] BacktestEngine 经 Provider 跑完真实 A 股区间，无异常退出
[PASS] 回测资产曲线 / 持仓来自真实价格，且与原表抽样对账一致
[PASS] 防未来数据机制生效（handle_data 仅见 current_dt 及之前）
[PASS] 补充 tests/unit/test_real_backtest.py 并全过
[PASS] BulletTrade registry 回归 + QuantRadar 全量测试保持全过
[PASS] 单一 commit 含 REAL_A_SHARE_BACKTEST_PASS
```

---

# 六、结束条件

```text
1. 实现真实 A 股回测（策略 + 引擎接入 + 对账 + 防未来数据断言）+ 测试
2. 更新 docs/CURRENT_STATE.md（Provider / 回测 PASS）
3. git diff --check 无遗留空白错误
4. 单一 commit（REAL_A_SHARE_BACKTEST_PASS）
5. push origin main
6. 将 ACTIVE_PHASE 改为 Phase 5（复权）-> 自动进入 Phase 5
```
