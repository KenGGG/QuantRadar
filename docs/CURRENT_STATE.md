# 当前状态

文件：`docs/CURRENT_STATE.md`

> 系统「记忆」，由 Codex 在每次 ACTIVE_PHASE 完成后维护。只记录**现在的事实**，不写流水账（历史在 Git）。
> 本文件由 Phase -1/0 审计首次填充。下一阶段以新的 ACTIVE_PHASE.md 为准，禁止自动进入。

---

# 当前阶段

```text
当前阶段：Phase 2B（原始日线 get_price）— 已完成
阶段标志：RAW_DAILY_PRICE_PASS
最近完成：get_price(fq='none') 日频原始价（final_a_stock_eod_price；单/多证券、start/end/count/fields、MultiIndex 面板、与原表抽样对账一致；fq!=none 与 frequency!=daily 明确 NotImplementedError；上市前/退市后/无数据窗口显式空不伪造）
QuantRadar 根 commit：见 git log（origin=KenGGG/QuantRadar）
BulletTrade 快照 base commit：be0451b（记录于 BASELINE.md；vendor/ 无 remote、无 .git）
```

---

## 当前可用（PASS）

```text
BulletTrade Ubuntu Core      PASS  （bullet-trade 0.9.2；BacktestEngine import OK；lab --diagnose OK）
QuantRadar Git 基线          PASS  （fork 为 vendor/bullet-trade 快照，QuantRadar 根自有仓库）
项目内 Python .venv          PASS  （python3.12.3；bullet-trade 以 editable 装入，指向 vendor/bullet-trade）
investment_data 可访问       PASS  （Dolt SQL server 127.0.0.1:3307，只读 SELECT 正常）
A 股日线                     PASS  （final_a_stock_eod_price，1990-12-19..2026-08-04，6129 标的）
交易日历                     PASS  （ts_trade_day_calendar，is_open=1 共 8797 日，1990-12-19..2026-12-31）
指数权重                     PASS  （ts_index_weight，6 指数，2005-04-08..2026-06-30）
指数成分                     PASS  （由 ts_index_weight 按 index_code 派生 stock_code）
涨跌停                       PASS  （final_a_stock_limit，pre_close/up_limit/down_limit）
ST 标记                      PARTIAL（bao_a_stock_eod_info.is_st ∈ {0,1}；bao 源仅至 2023-06-09）
Provider 源码审计             PASS  （7 问已回答，见下「Provider 机制」）
Generic Provider Registry    PASS  （Phase 1 实现：register_data_provider / unregister_data_provider，经 _create_provider 统一入口，见下）
Registry lifecycle           PASS  （Phase 1.1：unregister 清 Registry/cache/auth；overwrite 清旧 cache 并用新 factory；active global 不热切换；13/13 测试通过）
InvestmentDataProvider base  PASS  （Phase 2A：只读 Dolt 连接 + symbol mapping + get_trade_days / get_all_securities(PIT) / get_security_info / get_index_stocks(PIT) / get_index_weights(PIT)；38/38 QuantRadar 测试通过）
get_price 日频原始价          PASS  （Phase 2B：final_a_stock_eod_price，fq='none'，open/high/low/close/volume/amount 直读，绝不使用 adjclose；单/多证券、start/end/count/fields、与原表抽样对账一致；17 个新增测试通过）
QuantRadar Provider bootstrap IMPLEMENTED（Phase 2A：backend/quantradar/bootstrap.py 显式 register + set_active + 校验 name）
Qlib import                  PASS  （pyqlib 0.9.7 已装入 .venv）
```

---

## 当前 Blocked

```text
ETF                          BLOCKED（investment_data 无 ETF 表；Phase 11 前不建设）
alpha factor                 BLOCKED（investment_data 无因子表）
公司行为(分红/拆股)显式数据   LIMIT  （无独立表；仅 bao.adjfactor/adjclose 隐含，get_split_dividend 待建设）
Qlib 数据                     PARTIAL（import OK；QLIB_DATA_NOT_BUILT，全机无 qlib_data/cn_data）
停牌(tradestatus) 鲁棒性      PARTIAL（bao.tradestatus 列存在，语义与覆盖待 Phase 2 确认；bao 源至 2023-06-09）
InvestmentDataProvider       BASE IMPLEMENTED（Phase 2A）+ get_price PASS（Phase 2B）；get_split_dividend NOT IMPLEMENTED（Phase 5）
FastAPI / PostgreSQL / Worker / WebUI   BLOCKED（Phase 7/8 前）
Qlib 模型                     BLOCKED（Phase 10 前）
QMT / 实盘                    BLOCKED（未来实盘节点）
```

---

## 当前关键路径

```text
investment_data (Dolt 3307)
→ InvestmentDataProvider (Phase 1/2，实现 DataProvider ABC)
→ BulletTrade 回测 (Phase 4)
→ Snapshot / 可复现 (Phase 6)
→ Web 工作台 (Phase 7/8)
→ Qlib 高级研究 (Phase 10)
```

---

## 已验证事实（审计产物）

### 环境
- OS: Linux/Ubuntu（x86_64）；Python 3.12.3（目标 3.11 本机不可用，见风险）；Node v22.23.1。
- BulletTrade 基线：vendor/bullet-trade（BulletTrade v0.9.2，commit be0451b），无嵌套 .git。
- 安装：`pip install -e ./vendor/bullet-trade`；`import bullet_trade` → vendor/bullet-trade/bullet_trade/__init__.py。
- 附加：`pip install pyqlib==0.9.7`（仅验证 import）。

### investment_data（Dolt，14 表）
| 表 | 内容 | 规模 / 区间 |
|---|---|---|
| final_a_stock_eod_price | A 股日线主源（open/high/low/close/adjclose/volume/amount） | 18.3M 行；1990-12-19..2026-08-04；6129 标的；symbol 格式 `SH600601` |
| final_a_stock_limit | 涨跌停（pre_close/up_limit/down_limit） | 14.1M；1996-12-16..2023-06-12 |
| bao_a_stock_eod_info | 信息源（tradestatus 停牌 / is_st / adjfactor 复权因子 / adjclose / adjpreclose） | 14.3M；1990-12-19..2023-06-09；5183 标的 |
| ts_a_stock_eod_price | Tushare 日线源 | 18.0M |
| ts_a_stock_list | 证券主数据（ts_code `000001.SZ` / symbol `000001` / exchange / list_date / delist_date） | 5023 |
| ts_index_weight | 指数权重（index_code / stock_code `000001.SZ` / trade_date / weight） | 2.4M；6 指数；2005-04-08..2026-06-30 |
| ts_trade_day_calendar | 交易日历（exchange=SSE / date / is_open） | 13162；is_open=1 共 8797 日 |
| c_a_stock_eod_price / w_a_stock_eod_price / yahoo_a_stock_eod_price | 其他来源日线 | — |
| c_link_table / ts_link_table / yahoo_link_table | 跨源 symbol 映射（link_date / adj_ratio） | — |
| max_index_date | 指数最大日期（1 行） | — |

6 个指数：000300.SH、000852.SH、000905.SH、000906.SH、000985.SH、399300.SZ。

### Provider 机制（源码审计，回答 7 问）
1. **DataProvider ABC 接口**：`bullet_trade/data/providers/base.py`。抽象方法：`get_price`（含 `fq='pre'` 与 `pre_factor_ref_date`）、`get_trade_days`、`get_all_securities`、`get_index_stocks`、`get_split_dividend`；可选（默认抛 `NotImplementedError`）：`get_bars`、`get_ticks`、`get_index_weights`、`get_fundamentals`、`get_industry_stocks` 等。
2. **Provider 如何创建**：`bullet_trade/data/api.py:_create_provider(provider_name, overrides)` 工厂，按名称 import 并实例化具体类并注入配置；也可直接 `new` 实例传入 `set_data_provider`。
3. **是否已有外部注册机制**：**Phase 1 起为「是（通用注册表）」**。`providers/` 已有 jqdata/tushare/miniqmt/remote_qmt/rqdata/easy_tdx 实现；`_create_provider` 为硬编码 if 链（内置 Provider）。Phase 1 **新增 Generic Provider Registry**：`register_data_provider(name, factory, *, overwrite=False)` / `unregister_data_provider(name)`。注册后，`_create_provider` 会先查注册表，命中则用 `factory(merged_config)` 创建（统一入口、不复制逻辑）；未命中才走内置 if 链；未知名称仍 `ValueError`。
   - **不再**需要为外部 Provider（如未来的 `InvestmentDataProvider`）往 `_create_provider` 里加硬编码 `if target == "investment_data"` 分支；改为在 QuantRadar 侧用 `register_data_provider` 注册工厂，再 `set_data_provider(name)` 使用。
   - factory 契约：`factory(config: dict) -> DataProvider`（config = `get_data_provider_config()` 与 overrides 的合并）。
   - 内置 Provider 名称受保护，默认禁止外部覆盖（需显式 `overwrite=True`）。
   - 暴露位置：`bullet_trade.data.register_data_provider` / `unregister_data_provider`。
   - **生命周期（Phase 1.1）**：`register`（含 `overwrite=True`）会清除该名称既有 instance cache + auth state，使后续按名获取用（新）factory；`unregister` 清除 Registry/cache/auth 三者，但**不替换已激活的全局 `_provider`**；切换当前全局 Provider 必须显式 `set_data_provider(...)`。Registry 测试 13/13 通过。
   - **import 阶段初始化**：`bullet_trade.data.api` 在模块 import 时执行 `_provider = _create_provider()`（此时 Registry 为空，按 `DEFAULT_DATA_PROVIDER` 走内置 if 链）。因此 QuantRadar 必须在 import 之后、查询之前显式 `register_data_provider` + `set_data_provider`，不能依赖 `DEFAULT_DATA_PROVIDER=investment_data` 在 import 阶段自动注册（详见 03 的 Bootstrap 契约与配置边界）。
4. **set_data_provider 如何工作**：`api.set_data_provider(provider)` 接受实例或名称；实例直接存为全局 `_provider`，名称走 `_create_provider`；随后 `auth()`、绑定 sdk fallback、缓存、按需关闭 live 缓存。
5. **外层 get_price/history 如何调用 Provider**：`bullet_trade/data/api.py` 顶层 `get_price/history/get_trade_days` 直接调用全局 `_provider` 对应方法。
6. **BacktestEngine 如何取得 Provider**：`core/engine.py` import `get_data_provider`，回测中经 `get_data_provider()` 取全局 provider；并把 wrapped `set/get_data_provider` 注入策略命名空间，故策略内 `set_data_provider(...)` 即设置全局 provider。
7. **防未来数据机制**：(a) 结构性——引擎 `set_current_context(context)`，回测中 `get_price/history` 在 `end_date` 缺省时回退到 `_current_context.current_dt`（api.py ~1892-1915），只返回模拟“当前日”前数据；(b) 显式开关——`avoid_future_data=True` 时越界访问未来数据抛 `FutureDataError`（api.py ~1869）；复权锚点也用 `_current_context.current_dt`。

---

## 数据表映射（investment_data → Provider 方法）

```text
final_a_stock_eod_price      → get_price（原始价 + adjclose；symbol='SH600601'）
ts_trade_day_calendar        → get_trade_days（is_open=1 的 SSE 交易日）
ts_a_stock_list              → get_all_securities / get_security_info（上市/退市日期）
ts_index_weight              → get_index_weights + get_index_stocks（派生成分；stock_code='000001.SZ'）
final_a_stock_limit          → 涨跌停（可映射到 get_extras 或扩展方法）
bao_a_stock_eod_info         → is_st / tradestatus(停牌) / adjfactor(复权因子)
公司行为(分红/拆股)           → 无独立表；get_split_dividend 待建设（LIMIT）
```

**symbol 格式不一致（关键）**：`final` 用 `SH600601`、`index/list` 用 `000001.SZ`、`list` 另有裸 `000001`。Provider 必须归一化；`c/ts/yahoo link_table` 含 `adj_ratio` 可辅助跨源对齐。

---

## 风险

```text
R1  Python 支持范围 >=3.11,<3.13（本机仅 3.12.3 可用，已验证安装/导入通过）。3.11 不可用、3.13 未验证；后续升级需复测。
R2  symbol 多格式：Provider 必须做归一化，否则指数/日线对不齐。
R3  investment_data 多源湖（final/c/ts/w/yahoo），final_* 似主源；Phase 2 需定主源与去重。
R4  复权：final 仅 adjclose，原始 factor 只在 bao(adjfactor)；引擎已有 dynamic pre-factor 逻辑，Provider 需供给 raw price + factor。
R5  公司行为显式数据缺失；ETF 缺失；alpha factor 缺失。
R6  Qlib 数据未构建（QLIB_DATA_NOT_BUILT）。
R7  trade calendar 仅 SSE 行（A 股日历统一，可接受）。
R8  vendor 为快照，无 upstream 完整 git 历史；禁止向 upstream 推送（见 02 第二节）。
```

---

## 下一任务

```text
Phase 1（已完成）：Generic Provider Registry —— CUSTOM_PROVIDER_REGISTRATION_PASS
Phase 1.1（已完成）：Registry 生命周期加固 —— PROVIDER_REGISTRY_LIFECYCLE_PASS
Phase 2A（已完成）：InvestmentDataProvider 基础能力 —— INVESTMENT_DATA_PROVIDER_BASE_PASS
Phase 2B（已完成）：原始日线 get_price(fq="none") —— 基于 final_a_stock_eod_price，日频，与数据库原表抽样对账 —— RAW_DAILY_PRICE_PASS
Phase 3（下一阶段）：JoinQuant 兼容层（get_price/history/attribute_history 对齐 JQ 语义、复权因子读取、停牌/涨跌停语义对齐）
禁止提前开发：复权价 / FastAPI / React / PostgreSQL / Qlib / ETF / QMT / 实盘（除非当前阶段需要）
```
