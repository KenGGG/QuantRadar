# QuantRadar Active Phase

**Milestone:** `QUANTRADAR_DATAHUB_V1_PASS`
**Active Goal:** `DATAHUB_DAILY_UPDATE_REMEDIATION_PASS`
**Status:** COMPLETE

## Scope

用户于 2026-09-11 提供 DataHub 整改意见并要求统一在 main 开发。此前 DataHub 分支及 launcher 改动已合并到 main；Web 服务读取主工作区。旧 worktree 仅保留备查。

本轮交付真实失败对账、统一双库更新、候选检查与隔离发布、固定版本策略读取和简化的数据状态页。实施清单见 [整改计划](superpowers/plans/2026-09-11-datahub-remediation.md)，事实证据见 [验收记录](acceptance/datahub-remediation-2026-09-11/README.md)。

仅允许对配置好的可信基础 Dolt remote 做干净 fast-forward 同步；禁止基础表自制写入、硬重置、强制覆盖和绕开来源冻结。
未解决证券必须保留台账与隔离，不改分母、不虚构覆盖。历史版本保持可回放。基础行情能力不因补充字段缺口被全局锁死。
PIT_PARTIAL、跨源一致性未验及陈旧元数据必须如实保留。

## Acceptance

- P0：失败基线、未知空值/解析错误分类、台账竞争、冷却恢复、流式校验已实现并测试。
- P1：统一入口、目标水位、候选分支、内容幂等、固定 commit 验证已实现；正式发布与维护同步已通过。
- P2：三块页面与明确缺口的策略接口已实现；三种真实历史回测、新版本读取和页面自动刷新已通过。
- 验收记录已更新；本提交将同步 origin/main。

## Queued Goals

无。不自动进入新来源资格认定、FactorLab、NotebookLM、Qlib 或 Kronos。此前用户接受的整体 WebUI 布局不重新设计。
