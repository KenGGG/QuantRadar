# QuantRadar Active Phase

**Milestone:** `QUANTRADAR_DATAHUB_V2_TRUSTED_FUSION`
**Active Goal:** `DATAHUB_V2_HISTORICAL_REUSE_AND_INCREMENTAL_REPAIR`
**Status:** IN_PROGRESS

## Scope

用户于 2026-09-11 提供《QuantRadar DataHub：历史复用、渐进补数与可信融合实施方案 V2》，要求统一在 main 开发。此前 DataHub V1 整改仍是可复用基础；Web 服务读取主工作区。旧 worktree 仅保留备查。

本轮将基础库视为多来源历史资料，先扫描并复用 `final` 与已验证原表，再以获准的 AKShare/BaoStock 路径逐步补足真实缺口，最终发布带选源映射和使用说明的固定本地版本。实施清单见 [V2 P0 计划](superpowers/plans/2026-09-11-datahub-v2-p0-inventory.md)，V1 事实证据见 [既有验收记录](acceptance/datahub-remediation-2026-09-11/README.md)。

仅允许对配置好的可信基础 Dolt remote 做干净 fast-forward 同步；禁止基础表自制写入、硬重置、强制覆盖和绕开来源冻结。
未解决证券必须保留台账与隔离，不改分母、不虚构覆盖。历史版本保持可回放。基础行情能力不因补充字段缺口被全局锁死。
PIT_PARTIAL、跨源一致性未验及陈旧元数据必须如实保留。

## Acceptance

- P0：固定 release 的 schema 扫描器、库存产物与低 Beta 窗口工作单已完成。已发现 `final`、Tushare、BaoStock、Wind/财汇与 Yahoo 原表；基础行情无需重抓，ST/停牌尾部保持 UNKNOWN。
- P0：已核验 `000300.SH` 与 `399300.SZ` 在 2020-01-02 至 2022-07-01 的 47 个共同截面成分完全一致；别名只能限于该重叠区间。
- P1：腾讯原始日线已完成主板、创业板、科创板、指数四类样本资格检查；仅限字段/单位样本合格，尚未发布补丁。
- P2：BaoStock 单次登录和一会话三只股票的最小样本成功，原始响应可同时派生行情、状态与估值候选；23 条真实缺失状态记录（含低 Beta 首日 20 个实际持仓）已在独立部分 release 发布并通过回放。剩余尾部仍为 UNKNOWN。
- P3：旧、新 release 的原低 Beta 2023-09 回放均通过并产生相同哈希；状态补丁未触及该策略的实际状态依赖路径，差异归因为零。20 只股票的同机固定版本批量读取首读 115.804 ms、状态缓存热读中位数 13.205 ms，证据见 `acceptance/datahub-v2-p3/batch-read-benchmark.md`。
- P3：低 Beta 的真实状态依赖已预检：2024-01-02 的 300 个成分股没有当日状态记录。策略版本 139 在未知状态时排除证券，旧版及旧运行不变；证据见 `acceptance/datahub-v2-p3/low-beta-status-guard.md`。

## Queued Goals

无。在本目标结束前不进入 FactorLab、NotebookLM、Qlib 或 Kronos。此前用户接受的整体 WebUI 布局不重新设计。
