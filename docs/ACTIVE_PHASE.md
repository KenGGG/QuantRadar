# QuantRadar Active Phase

**Milestone:** `QUANTRADAR_DATAHUB_V1_PASS`
**Active Goal:** `DATAHUB_INGESTION_MVP_PASS`
**Completed Goal:** `JOINQUANT_LAYOUT_BROWSER_ACCEPTANCE_PASS`
**Status:** IN_PROGRESS

## 唯一目标与授权范围

用户于 2026-09-09 批准 DataHub V1，并明确确认 WebUI 布局验收通过。
WebUI 收尾提交 `ec608d8`；布局工作结束，不继续扩展。
DataHub 完整范围与验收契约见
[批准需求](superpowers/specs/2026-09-09-datahub-v1.md)。

原 `DATAHUB_REPRODUCIBLE_PIT_V1_PASS` 与 `DATAHUB_GOVERNED_REPRODUCIBLE_V1_PASS`
已被本 Goal superseded，均未标记 PASS。
只补沪深 A 股历史估值 PE_TTM/PB_MRQ/PS_TTM/PCF_OCF_TTM、申万一级行业历史、
含退市股票的生命周期。复用 investment_data 的 turn/is_st/tradestatus。
基础库只读，补充数据仅写 /data/quantradar_data Dolt；PostgreSQL 仅存应用状态。
`pcf_ncf_ttm` 是已暂停 BaoStock 路线的原计划字段；Eastmoney 的
`PCF_OCF_TTM` 作为 V1 canonical `pcf_ocf_ttm`，二者不存在语义别名。
固定源代码与原始结果；按数据集标记 PIT_STATUS，不把历史回填冒充严格 PIT。
以原子 release manifest 固定两个库的 commit，所有研究/回测实际按锁定版本查询。

## Sequential Gates（仅一个 Active Goal）

- Gate MVP-0 IN_PROGRESS：将成熟下载工程模式映射到现有 journal/staging/Dolt；完成
  per-shard 状态、heartbeat、单一 updater lock、SIGTERM 保存、dry-run/audit/gap report、repair 和最小 CLI。
- Gate MVP-1 PENDING：以 per-symbol Eastmoney 回填当前可得 2018+ 估值，20→100→500→remaining；
  2016–2017 与退市估值记为 `NOT_COVERED`，允许 `PARTIAL`。
- Gate MVP-2 PENDING：SW 历史与 partial lifecycle（base/SSE/明确 approximation）进入 staging/audit。
- Gate MVP-3 PENDING：发布首个 PARTIAL 双 Dolt release，固定读取、旧 release 重跑、WebUI/systemd 验收。
- Gate 0 PASS：只读现有库审计和申万直连边界见 `docs/acceptance/datahub-v1/`。BaoStock 全部真实请求已暂停；
  623 个 unpublished shards、journal、raw/hash 和错误证据冻结，永不发布或混入新 canonical 数据。
- Gate 1 PENDING：以 Eastmoney date-slice、SSE/SZSE lifecycle、既有 SW adapter 完成最小闭环。
- Gate 2 PENDING：backfill/sync/audit/release 与固定版本读取。
- Gate 3 PENDING：复用数据状态页面，CLI，20:00 Asia/Shanghai systemd timer。
- Gate 4 PENDING：十二项真实验收，特别是更新后旧 release 重跑结果 hash 一致。

按 Gate 0→4 顺序执行；普通错误自行修复；不因任务规模或普通测试失败停止。
通过后更新 CURRENT_STATE 和本文件、提交证据与代码，然后停止。

## Queued Goals

无。不自动进入 FactorLab、AI 策略复现或下一批数据扩展。
NotebookLM、Qlib、Kronos 原暂停状态保持。

## 7231 数据状态页面事实

正式端口已加载 datahub-v1 页面，任务 / Governor / 正式覆盖 / 折叠诊断分层展示；浏览器与 45 项 DataHub 单测通过。详情见 [布局验收](acceptance/datahub-v1/webui-7231-layout.md)。002504 的 SDK `NoneType` 解析异常曾错误打开 circuit，现已作为 `SYMBOL_DATA_ERROR` 审计并解除 false-positive cooldown；worker 正在从 `PENDING` 串行恢复。控制与发布完整验收未完成，Goal 仍为 IN_PROGRESS。
