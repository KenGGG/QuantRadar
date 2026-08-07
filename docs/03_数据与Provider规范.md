# 数据与 Provider 规范

文件：`docs/03_数据与Provider规范.md`

本文件是 QuantRadar 最重要的技术规范之一。
它定义数据事实源、统一 Provider 接口、数据语义与能力评估方法。

回测如何使用数据见 `04`，Qlib 数据导出见 `06`。

---

# 一、Source of Truth

```text
/data/investment_data  = 唯一正式数据事实源
```

```text
禁止：investment_data 失败 → 自动切换 JQData / Tushare / AkShare
允许：使用其他源做对账（不写回 investment_data）
数据不足：显式 BLOCKED，不伪造
```

investment_data 默认只读，禁止：

```text
INSERT / UPDATE / DELETE / ALTER
DOLT PULL / DOLT COMMIT
```

（审计阶段只读查询，见 ACTIVE_PHASE 第五节。）

---

# 二、InvestmentDataProvider

QuantRadar 通过统一的 `InvestmentDataProvider` 接入 investment_data。

```text
InvestmentDataProvider
├── 实现 BulletTrade DataProvider ABC
├── 读取 /data/investment_data（Dolt / Parquet）
├── 提供 get_price / get_trade_days / security master / 指数 / 因子
├── 处理复权与公司行为（见第五节）
└── 保证 Point-in-Time（见第六节）
```

Provider 不得：

```text
不得修改 BulletTrade 撮合逻辑
不得伪造缺失数据
不得隐藏 BLOCKED / LIMIT 状态
```

---

# 三、Provider 注册机制

目标：使 BulletTrade 能正式注册 investment_data 为外部 Provider。

```text
set_data_provider(InvestmentDataProvider(...))
```

需从源码审计回答（ACTIVE_PHASE 第七节）：

```text
1. DataProvider ABC 当前接口是什么？
2. Provider 如何创建？
3. 是否已有外部 Provider 注册机制？
4. set_data_provider 如何工作？
5. get_price / history 等外层如何调用 Provider？
6. BacktestEngine 如何取得 Provider？
7. 防未来数据机制在哪里？
```

注册规则：

```text
Provider 通过公开注册入口挂入，不 monkey-patch 核心
若 BulletTrade 无注册机制，最小改动补充，并写回归测试证明
```

---

# 四、核心数据接口

## 4.1 symbol mapping

```text
内部统一符号约定（如 600000.XSHG）需在 Provider 内映射
支持：A 股股票、指数、ETF（ETF 受 Phase 11 门禁约束）
禁止：在策略层散落多种符号格式
```

## 4.2 get_price

```text
get_price(symbol, start, end, freq='1d', fq='pre'|'post'|'none')
返回字段：open/high/low/close/volume/...
fq='pre' 需要 pre_factor_ref_date（见第五节）
缺失交易日 / 停牌：显式标记，不插值成虚假价格
```

## 4.3 get_trade_days

```text
返回交易日历（来自 investment_data 交易日历表）
回测区间必须以真实交易日历为准，禁止自行生成日历
```

## 4.4 security master

```text
证券代码主数据：上市/退市日期、类型、交易所、停牌、ST 标记
策略与回测依赖它判断可交易集合与 Point-in-Time 有效性
```

## 4.5 index constituents / index weights

```text
指数成分（如沪深300）：给定日期返回成分股列表（PIT）
指数权重：给定日期返回权重
用于指数动量、基准比较、组合约束
```

## 4.6 factor

```text
因子数据以 Parquet / 表形式提供，按 symbol + date 索引
缺失因子：显式 BLOCKED 或 LIMIT，禁止用 adjclose 冒充（见 00 第四节）
```

---

# 五、复权与公司行为

```text
raw price：未复权原始价格
factor：复权因子序列
fq='pre'：以 pre_factor_ref_date 为复权基准向前复权
pre_factor_ref_date：前复权参考日，必须来自数据，禁止硬编码假设
dividend / split：公司行为，影响 factor 与会计（见 04）
```

规则：

```text
复权必须由数据驱动，不得用 close 自行推算 factor
缺公司行为 → 显式标记，禁止假设「没有分红」
缺 factor → 返回 BLOCKED，禁止用 adjclose 冒充
```

---

# 六、Point-in-Time（PIT）

```text
任何在回测时点 t 使用的数据，必须是 t 时点已可获得的数据
禁止未来函数：不得用 t 之后才发布/修正的数据
指数成分、公司行为、因子、财务都需 PIT 校验
```

Provider 负责在数据访问层截断未来可见性；回测引擎不依赖此假设（见 04）。

---

# 七、Provider Acceptance（能力验收）

Provider 完成后需逐能力验收，状态使用统一能力矩阵。

## 7.1 Capability Matrix 状态定义

```text
PASS        能力完整、数据齐备、测试通过
PARTIAL     能力可用但有已知限制（需记录限制范围）
LIMIT       仅部分市场/部分字段可用（明确边界）
UNSUPPORTED 当前架构明确不支持（记录原因）
BLOCKED     数据缺失或依赖未就绪，不可使用（必须显式）
FAIL        已实现但测试不通过（缺陷，需回归测试）
```

## 7.2 验收清单（节选）

```text
A股日线            PASS / BLOCKED
交易日历          PASS / BLOCKED
证券主数据        PASS / PARTIAL / BLOCKED
指数成分          PASS / BLOCKED
指数权重          PASS / BLOCKED
复权 raw+factor   PASS / PARTIAL / BLOCKED
公司行为          PASS / BLOCKED
涨跌停 / 停牌 / ST PASS / PARTIAL / BLOCKED
因子              PASS / PARTIAL / BLOCKED
ETF               BLOCKED（Phase 11 前）
```

每个非 PASS 状态都必须记录：

```text
哪个 symbol / 字段 / 日期范围
为什么（数据缺失 or 架构限制）
对回测的影响
```

---

# 八、数据表映射

investment_data 真实表名 → Provider 方法 的映射，由 CURRENT_STATE 记录
（审计阶段以真实查询为准，禁止凭 README 猜测，见 ACTIVE_PHASE 第五节）。

---

# 九、与其他文档关系

```text
00 入口：数据正确性优先、不伪造
01 边界：investment_data 是事实源，ETF 独立门禁
04 回测：Provider 如何被 BulletTrade 使用、可复现
06 Qlib：Provider 数据导出为 Qlib 格式
```
