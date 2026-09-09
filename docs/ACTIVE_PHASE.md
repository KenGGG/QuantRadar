# QuantRadar Active Phase

**Milestone:** `QUANTRADAR_DATAHUB_V1_PASS`
**Active Goal:** `DATAHUB_REPRODUCIBLE_PIT_V1_PASS`
**Completed Goal:** `JOINQUANT_LAYOUT_BROWSER_ACCEPTANCE_PASS`
**Status:** IN_PROGRESS

## 唯一目标与授权范围

用户于 2026-09-09 批准 DataHub V1，并明确确认 WebUI 布局验收通过。
WebUI 收尾提交 `ec608d8`；布局工作结束，不继续扩展。
DataHub 完整范围与验收契约见
[批准需求](superpowers/specs/2026-09-09-datahub-v1.md)。

只补沪深 A 股历史估值 PE_TTM/PB_MRQ/PS_TTM/PCF_NCF_TTM、申万一级行业历史、
含退市股票的生命周期。复用 investment_data 的 turn/is_st/tradestatus。
基础库只读，补充数据仅写 /data/quantradar_data Dolt；PostgreSQL 仅存应用状态。
固定源代码与原始结果；按数据集标记 PIT_STATUS，不把历史回填冒充严格 PIT。
以原子 release manifest 固定两个库的 commit，所有研究/回测实际按锁定版本查询。

## Sequential Gates（仅一个 Active Goal）

- Gate 0 IN_PROGRESS：只读现有库审计，三个来源本机真实取数，记录边界。
- Gate 1 PENDING：最小 DataHub 闭环及三个数据集。
- Gate 2 PENDING：backfill/sync/audit/release 与固定版本读取。
- Gate 3 PENDING：复用数据状态页面，CLI，20:00 Asia/Shanghai systemd timer。
- Gate 4 PENDING：十二项真实验收，特别是更新后旧 release 重跑结果 hash 一致。

按 Gate 0→4 顺序执行；普通错误自行修复；不因任务规模或普通测试失败停止。
通过后更新 CURRENT_STATE 和本文件、提交证据与代码，然后停止。

## Queued Goals

无。不自动进入 FactorLab、AI 策略复现或下一批数据扩展。
NotebookLM、Qlib、Kronos 原暂停状态保持。
