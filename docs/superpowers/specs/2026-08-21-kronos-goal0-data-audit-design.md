# Kronos Goal 0 数据事实审计设计

## 目标

仅实现 PRD v2.0 的 Goal 0：以只读方式审计本机 `/data/investment_data`，输出可复现的数据契约、证据表和真实门禁。完成后停止，不开发 Kronos 运行时、信号、组合、回测、API 或 WebUI。

## 边界

- 事实源仅为当前 Dolt 数据库，不使用外部数据、mock 或随机数据补缺。
- 不修改 `InvestmentDataProvider` 和 BulletTrade 行为；审计代码放在独立 `quantradar.kronos.data_audit` 包。
- 运行开始和结束的 Dolt HEAD 必须一致；变化时失败且不发布正式报告。
- 所有抽样确定且可复现，报告显式区分 `PASS`、`PARTIAL`、`BLOCKED`、`FAIL`。
- 公司行为没有独立事实表时，只能审计代理证据，不得宣称事件类型或账户会计完整通过。

## 组件

- `models.py`：状态枚举、表规格、JSON 安全序列化和门禁结构。
- `schema.py`：指定表的真实 schema、日期覆盖、重复键、关键字段空值率。
- `prices.py`：确定性选择至少 30 只股票，核验原始价、前后复权、量额口径和事件窗口连续性。
- `actions.py`：从 `adjfactor` 与 `preclose` 变化选择至少 20 个真实候选事件，输出事件证据和可/不可验证项。
- `universe.py`：选择至少 20 个历史周度日期，将 Provider 结果与 `MAX(trade_date) <= audit_date` 的原表快照对账。
- `gates.py`：只根据证据推导 PRD 七项数据门禁。
- `report.py`：以临时目录生成 CSV、Markdown、JSON，最后原子发布。
- `runner.py`：编排审计、校验 Dolt HEAD 和构建 manifest。
- `scripts/kronos_data_audit.py` 与 `make kronos-data-audit`：用户入口。

## 数据契约

`data_contract.json` 至少说明：

- `raw_open/high/low/close` 来自 `final_a_stock_eod_price` 原始 OHLC；
- `adjusted_open/high/low/close` 的 hfq/qfq 计算规则；
- `adj_factor = adjclose / close` 的适用条件与参考日；
- `volume`、`amount` 不随价格复权；
- `pre_close`、真实涨跌停、ST、tradestatus 和公司行为代理字段的来源、覆盖及限制。

契约结论必须由本次审计证据支持，不能硬编码为 PASS。

## 审计和门禁规则

1. 六张 PRD 指定表必须记录真实列名和日期覆盖；字段与 PRD 名称不同也应正常报告。
2. 价格样本覆盖沪深主板、创业板、科创板、不同价位、多个年份、因子变化和零成交情形。样本不足时不补造，相关门禁降级。
3. `none` 与原始 OHLC 对账；`hfq/post` 与 `adjclose` 对账；`qfq/pre` 使用显式参考日；volume/amount 保持原值。
4. 公司行为候选至少 20 个。缺少独立事件类型、送转比例、现金红利事实字段时，`corporate_action_ready=false`。
5. PIT 检查至少 20 周，Provider 与原表历史快照集合完全一致且快照不晚于审计日才可通过内部防倒灌检查。
6. 最新覆盖按字段分别报告；不能以价格最新日期替代 ST、停牌、涨跌停、公司行为或股票主数据日期。
7. `signal_research_ready` 只在价格语义和 PIT 宇宙满足最低条件时为真；`formal_backtest_ready` 还要求公司行为及交易状态足够完整；`real_assist_data_ready` 要求全部最新可交易状态完整。

## 输出

默认目录 `reports/kronos/data_audit/`：

- `price_semantics.csv`、`price_semantics.md`
- `corporate_actions.csv`
- `pit_universe_checks.csv`
- `coverage.csv`、`schema.json`
- `data_contract.json`、`data_gate.json`
- `audit_manifest.json`

JSON 使用排序键和 ISO 日期；CSV 使用稳定列序与稳定排序，保证相同 Dolt HEAD 下可复核。

## 错误处理

- 连接失败、表缺失、Dolt HEAD 变化或无法生成最小证据集：命令非零退出。
- 数据能力缺失但审计可完成：命令成功生成报告，门禁为 `PARTIAL/BLOCKED`。
- 任何未处理异常不吞掉，也不留下看似完整的正式输出目录。

## 测试

- 纯逻辑单测：序列化、状态聚合、门禁推导、确定性采样、复权计算、报告稳定性。
- `requires_dolt` 集成测试：真实 schema/覆盖、30 只价格样本、20 个公司行为候选、20 周 PIT 对账、Dolt HEAD 稳定性。
- CLI 测试运行真实审计并断言全部规定产物和真实门禁，不断言必须 PASS。

