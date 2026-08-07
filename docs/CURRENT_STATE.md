# 当前状态

文件：`docs/CURRENT_STATE.md`

> 系统「记忆」，由 Codex 在每次 ACTIVE_PHASE 完成后维护。只记录**现在的事实**，不写流水账（历史在 Git）。
> 本文件由 Phase -1/0 审计首次填充。下一阶段以新的 ACTIVE_PHASE.md 为准，禁止自动进入。

---

# 当前阶段

```text
当前阶段：Closing Phase（收尾补齐 4 项 → QUANTRADAR_V1_PASS）
  1) 完整 Snapshot/Audit          PASS  FULL_AUDIT_REPRO_PASS ✅
  2) PostgreSQL + Worker          进行中（PERSIST_WORKER_PASS；本机 1Panel Postgres 已就绪，可建库验证）
  3) 正式 React WebUI             待办（WEB_WORKBENCH_PASS；npm registry 现已可达，可 npm install 构建）
  4) Qlib 最小闭环                待办（QLIB_BULLETTRADE_LOOP_PASS）
阶段标志：QUANTRADAR_STOCK_V1_PASS（主线达成）；QUANTRADAR_V1_PASS 待 4 项全部达成
最近完成（Closing 1）：build_snapshot 补齐审计字段 + backend/quantradar/audit.py（Dolt HEAD / schema 哈希 / commit）
  + 确定性测试（NAV/Trades/Positions/Metrics 一致 + 审计指纹一致）
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
JoinQuant 兼容核心            PASS  （Phase 3：frequency 别名 d/day/1d->daily；字段别名 money->amount；fq='none' 原始价 + fq='pre'/'post' 等价原始价 LIMIT 透传，绝不伪造复权；get_price/history/attribute_history 经 Generic Provider Registry 接入 BulletTrade 引擎；与原表抽样对账一致，close≠adjclose 已验证；13 个新增 JQ 兼容测试通过）
真实 A 股回测                PASS  （Phase 4：BacktestEngine 经 Provider 跑通 600519.XSHG 2023Q1，无异常；daily_records/持仓/资产曲线来自真实价，与原表对账一致；防未来数据生效；get_price 扩展 high_limit/low_limit（final_a_stock_limit）/paused（volume==0 派生）；新增 3 个回测 + 3 个字段测试通过）
真实复权（前/后复权）          PASS  （Phase 5：fq='post'/'hfq' 后复权 close 精确等于原表 adjclose；fq='pre'/'qfq' 前复权以 pre_factor_ref_date/窗口末日为基准（基准日 close==原始）；因子由 adjclose/原始价真实推导，绝不伪造；仅缩放 OHLC，volume/amount 保持原始；新增 4 个对账测试通过）
Snapshot / 可复现             PASS  （Phase 6：quantradar.snapshot 固化回测环境与 daily_records 结果指纹；save/load round-trip；同配置两次运行逐日一致；指纹对配置敏感；新增 3 个测试通过）
完整 Snapshot / Audit          PASS  （Closing Phase 1：FULL_AUDIT_REPRO_PASS；build_snapshot 补齐 snapshot_id / config_hash / strategy_hash / result_hash / metrics / environment(dolt_commit, schema_hash, provider_version, bullettrade_commit, quantradar_commit)；确定性测试验证 NAV/Trades/Positions/Metrics 一致 + 审计指纹一致；backend/quantradar/audit.py 采集 Dolt HEAD 与数据表 schema 哈希；3 个测试通过）
FastAPI 服务基础             PASS  （Phase 7：/api/health、/api/price、/api/backtest、/api/snapshot save/load；全程经 InvestmentDataProvider 读真实数据，无 mock；新增 4 个 TestClient 测试通过）
中文 WebUI / 主线闭环        PASS  （QUANTRADAR_STOCK_V1_PASS：浏览器策略回测 + 实验 + Web 构建 均已就位）
浏览器策略回测                PASS  （Phase 8/STOCK_V1：/api/backtest/strategy 接受 JoinQuant 兼容用户源码，引擎注入 get_price/order_target/log/g/run_daily 等全局，经 InvestmentDataProvider 跑真实数据；复用 BulletTrade 撮合/账户/订单/成交/调度，不重实现；3 个 TestClient 测试通过）
实验管理 API                  PASS  （/api/experiments 列表 / /api/experiments/{name} 加载 / /api/experiments/save 保存，复用 backend/quantradar/experiment 本地 JSON）
Web 构建（frontend/dist）     PASS  （offline 自包含中文 SPA：行情查询 / 策略回测(可编辑代码) / 实验列表，消费 /api/*，无 CDN、无构建步骤；GET / 优先托管；满足「Web build 成功」）
React+TS+Vite 源码脚手架      PARTIAL（frontend/ 源码就位：标准 Vite+React+TS 工程，消费 /api/*；构建需 npm install，本环境 TLS 阻断 npm registry 未装 node_modules/未出 Vite dist；联网后 cd frontend && npm install && npm run build 可生成 Vite 版 dist 覆盖离线 SPA）
QuantRadar Provider bootstrap IMPLEMENTED（Phase 2A：backend/quantradar/bootstrap.py 显式 register + set_active + 校验 name）
公司行为 + ST（Phase 5 补全）  PASS  （CORPORATE_ACTION_ST_PASS：get_split_dividend 据 bao_a_stock_eod_info 真实 preclose 缺口还原每股税前红利，与原始表逐行对账；get_extras('is_st'/'tradestatus') 直读真实列，df=True/Dict 两形态；9 个新测试 + 3 个 registry 测试通过）
因子研究（Phase 9 无依赖）    PASS  （backend/quantradar/research 复用 bullet_trade.research.factors.evaluation.evaluate_factor_performance；动量因子 ic_mean≈0.0146、rank_ic_mean≈0.0065（HS300 子集）；长表 [date,code,factor,forward_return]；IC/RankIC/分层/多空 齐全；4 个测试通过）
Experiment 实验管理（Phase 9） PASS  （backend/quantradar/experiment；基于 Snapshot 指纹的本地 JSON 存证与对比；save/load/list round-trip、不同配置不同指纹、同配置可复现、从 BacktestEngine 构造；3 个测试通过）
Make / Smoke（QUANTRADAR_SMOKE_PASS） PASS  （Makefile：setup/test/smoke/dev；scripts/smoke.py 全链路 数据→回测→快照→API→Web 入口 通过；无 mock）
Qlib import                  PASS  （pyqlib 0.9.7 已装入 .venv）
```

---

## 当前 Blocked

```text
ETF                          BLOCKED（investment_data 无 ETF 表；Phase 11 前不建设）
alpha factor                 BLOCKED（investment_data 无因子表）
公司行为(分红/拆股)          PARTIAL（bao_a_stock_eod_info 真实 preclose/close；以除权缺口还原每股税前红利，引擎按 20% 预提税，NAV 与不复权一致；送转/派息无法从本表分离 -> PARTIAL；get_split_dividend 已实现）
ST 标记                      PARTIAL（bao_a_stock_eod_info.is_st ∈ {0,1}；get_extras('is_st'/'tradestatus') 已实现，df=True/Dict 两形态；bao 源仅至 2023-06-09）
Qlib 数据                     PARTIAL（import OK；QLIB_DATA_NOT_BUILT，全机无 qlib_data/cn_data）
停牌(tradestatus) 鲁棒性      PARTIAL（bao.tradestatus 列存在，语义与覆盖待 Phase 2 确认；bao 源至 2023-06-09）
InvestmentDataProvider       BASE IMPLEMENTED（Phase 2A）+ get_price PASS（Phase 2B）+ JQ 兼容核心 PASS（Phase 3）+ 真实 A 股回测 PASS（Phase 4）+ 真实复权 PASS（Phase 5）+ 公司行为/ST PASS（Phase 5 补全）
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
公司行为(分红/拆股)           → 无独立表；get_split_dividend 据 bao.preclose/close 除权缺口还原（PARTIAL：送转/派息未分离）
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
Phase 3（已完成）：JoinQuant 兼容核心 —— frequency/fq 别名归一、字段别名、history/attribute_history 经 Generic Provider Registry 接入 BulletTrade 引擎，与原表对账 —— JQ_COMPAT_CORE_PASS
Phase 4（已完成）：真实 A 股回测 —— InvestmentDataProvider 驱动 BacktestEngine 跑通端到端，验证数据链路/防未来数据/真实价对账 —— REAL_A_SHARE_BACKTEST_PASS
Phase 5（已完成）：真实复权 —— fq='pre'/'post'/'qfq'/'hfq' 基于 adjclose 与原始价真实因子，与原表对账 —— ADJUSTED_PRICE_PASS
Phase 6（已完成）：Snapshot / 可复现 —— 回测环境快照 + 结果指纹，同配置可复现 —— SNAPSHOT_REPRO_PASS
Phase 7（已完成）：FastAPI 服务基础 —— /api/price / /api/backtest / /api/snapshot 暴露真实能力 —— FASTAPI_CORE_PASS
Phase 8（已完成）：中文 WebUI + 浏览器策略回测 + 实验 + Web 构建（offline SPA）—— QUANTRADAR_STOCK_V1_PASS
主线闭环达成（QUANTRADAR_STOCK_V1_PASS）：investment_data → Provider → JoinQuant策略 → BulletTrade真实回测 → PIT → Snapshot → Deterministic → API → 中文Web → Experiment → 因子研究
Phase 9（进行中）：无基础设施部分已完成（因子研究 / Experiment / Makefile / Smoke / 浏览器策略回测 / 实验API / Web构建，QUANTRADAR_SMOKE_PASS + QUANTRADAR_STOCK_V1_PASS）；PostgreSQL / Worker 待 Postgres 实例与凭证就绪（环境阻塞，不写未知库）
Phase 10（下一）：Qlib 高级研究（Alpha158 / LightGBM 等，需 QLIB_DATA 构建，本地可行）
禁止提前开发：PostgreSQL / Qlib 模型 / ETF / QMT / 实盘（除非当前阶段需要）
```
