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

- P0：固定 release 的 schema 扫描器已开始实现。已发现 `final`、Tushare、BaoStock、Wind/财汇与 Yahoo 原表；真实覆盖与字段清单待写入正式库存产物。
- P0：已核验 `000300.SH` 与 `399300.SZ` 在 2020-01-02 至 2022-07-01 的 47 个共同截面成分完全一致；别名只能限于该重叠区间。
- P1–P3：尚未开始；不得以 V1 的东财估值发布替代 V2 的价格/状态融合验收。

## Queued Goals

无。在本目标结束前不进入 FactorLab、NotebookLM、Qlib 或 Kronos。此前用户接受的整体 WebUI 布局不重新设计。
