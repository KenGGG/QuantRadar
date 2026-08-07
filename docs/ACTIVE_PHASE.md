# QuantRadar 当前开发任务

文件：`docs/ACTIVE_PHASE.md`

**当前阶段：Phase 2B — 原始日线（Raw Daily Price）**

```text
上一阶段 Phase 2A 已完成（INVESTMENT_DATA_PROVIDER_BASE_PASS）：
  - QuantRadar 包（backend/quantradar）+ 只读 Dolt 连接 + symbol mapping
  - get_trade_days / get_all_securities(PIT) / get_security_info / get_index_stocks(PIT) / get_index_weights(PIT)
  - bootstrap 层（register + set_active + 校验 name）；38/38 QuantRadar 测试通过
本阶段只做 Phase 2B；完成后自动进入 Phase 3（无人值守）。
```

---

# 一、目标

在已落地的 `InvestmentDataProvider` 之上实现日频原始行情：

```text
get_price(fq="none")
```

数据源优先级：`final_a_stock_eod_price`（字段 open/high/low/close/volume/amount，symbol 形如 SH600519）。

```text
不得 mock
不得返回虚假数据
不得用 adjclose 冒充原始价
```

---

# 二、范围与边界（强制）

```text
允许：
  - 在 backend/quantradar/providers/investment_data/provider.py 实现 get_price
  - 仅日频（frequency='daily'）；分钟级 UNSUPPORTED（raise 或明确不支持）
  - 支持 security（str 或 List[str]）、start_date、end_date、count、fields、多证券 panel
  - 与原表抽样对账（open/high/low/close/volume/amount 数值一致）
  - 新增/补齐 tests/unit 测试

禁止：
  - 实现复权（fq='pre' / factor）—— 那是 Phase 5
  - 改动 BulletTrade 核心
  - 写入 investment_data
  - 扩大至 ETF / QMT / 实盘
```

---

# 三、get_price 契约

签名（与 BulletTrade DataProvider ABC 对齐）：

```python
get_price(security, start_date=None, end_date=None, frequency='daily',
          fields=None, skip_paused=False, fq='none', count=None,
          panel=True, fill_paused=True, pre_factor_ref_date=None, ...)
```

要求：

```text
1. 返回 pandas.DataFrame；多证券 panel=True 时索引=日期、列=MultiIndex(字段, 证券)
2. fq='none'：直接返回 final_a_stock_eod_price 的原始 open/high/low/close/volume/amount
3. frequency 仅 'daily' 支持；非 daily 抛 NotImplementedError（分钟 UNSUPPORTED）
4. security 经 normalize_stock_symbol 转为 SH600519 形式查 final_a_stock_eod_price.symbol
5. start/end/count 语义与 JoinQuant 一致；count 与 start/end 组合按既有约定
6. skip_paused / fill_paused：若数据不足（停牌/缺行）必须显式 PARTIAL，不得假装完整
```

---

# 四、原始价对账（必须）

```text
固定或随机抽样若干 (symbol, 日期窗口)
Provider 返回 vs investment_data.final_a_stock_eod_price 原表
要求 open/high/low/close/volume/amount 数值一致（允许浮点容差）
```

对账测试作为新增测试的一部分，禁止用「接近」掩盖差异。

---

# 五、测试

至少覆盖（Phase 2A 已搭好 DB 测试 fixture）：

```text
- 单证券普通窗口（600519.XSHG / 000001.XSHE）
- 较早历史窗口
- count 取最近 N 日
- fields 选择子集
- 多证券 panel
- 无数据窗口（返回空 / 显式 BLOCKED）
- 上市前 / 退市后（显式空或 PARTIAL）
- 与原表抽样对账
- frequency != daily -> NotImplementedError
```

运行：

```text
tests/unit （pytest）
BulletTrade registry 回归（test_provider_registry.py）保持全过
```

---

# 六、验收

完成标志：`RAW_DAILY_PRICE_PASS`

```text
[PASS] get_price(fq='none') 日频实现
[PASS] 单/多证券、start/end/count/fields 正确
[PASS] 与原表抽样对账一致
[PASS] 上市前/退市后/无数据窗口 显式处理（不伪造）
[PASS] QuantRadar 新增测试通过 + BulletTrade registry 回归通过
[PASS] 单一 commit 含 RAW_DAILY_PRICE_PASS
```

---

# 七、结束条件

```text
1. 实现 get_price（日频原始价）+ 对账测试
2. 更新 docs/CURRENT_STATE.md（Provider 状态、get_price PASS）
3. git diff --check 无遗留空白错误
4. 单一 commit（RAW_DAILY_PRICE_PASS）
5. push origin main
6. 将 ACTIVE_PHASE 改为 Phase 3 → 自动进入 Phase 3
```
