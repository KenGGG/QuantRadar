# QuantRadar Active Phase

**Milestone:** `DATAHUB_V3_RESEARCH_DATA_EXPANSION`
**Active Goal:** `DATA_V3_P0_CANONICAL_DATA_FOUNDATION`
**Status:** IN_PROGRESS

## Scope

在既有双 Dolt、ReleaseReader、Provider、Publication 和 CLI 上建设两类研究事实：从当前开始累计的版本化指数快照，以及五只样本股票的可审计财务 canonical。基础 Dolt 只读；所有新事实必须走 raw evidence → candidate/quality → supplemental Dolt commit → release manifest，研究和回测不得联网或静默 fallback。

本轮唯一顺序为 **G0 → G1 → G2 → G3**。任何不能证明日期语义、单位、版本或来源的数据可以保存为 raw evidence，但不得提升为严格 PIT canonical。

## Acceptance

### DataHub V3 P0 gates

- **G0 Source Audit — PASSED.** 已归档 CSI300/500/1000 成分和权重、申万一级样本及五只股票三表的真实 AKShare 原始响应；普通企业、银行与保险 schema 已实测不同。中证权重单位为 PERCENT；申万权重仍是 UNIT_UNVERIFIED raw。所有当前历史财务响应均为 PIT_PARTIAL。详见 [G0 审计](acceptance/datahub-v3/g0_source_audit.md)。
- **G1 Index Snapshot — PASSED.** `qr_index_snapshot_version` 与成员表已在固定 release 发布 CSI300/500/1000 和申万样本；业务 `content_hash` 不含抓取元数据或行顺序，同内容实测 `NO_CHANGE`，变化会追加 revision。正式 CLI 仅在固定 SSE 交易日 20:30 Asia/Shanghai 后执行；申万仅在周五取得实际快照且不补造日期。首个 release 与复读结果见 [G1 记录](acceptance/datahub-v3/g1_first_snapshot_release.md)。
- **G2 Financial Canonical — PASSED.** 五只样本的三表 raw version 与 mapping 已在 `R8c64f7d5276fbdb7` 发布；固定 commit 核验 1,214 个不可变 statement versions、5 个证券，所有记录均为 `CANONICAL_PIT_PARTIAL`。原公告事实与 `conservative_available_at`/规则版本分开；银行、保险只验证 schema 与 NULL 语义。它不代表全市场或严格 PIT 财务回测资格。
- **G3 Release & Replay — IN_PROGRESS.**
- **G3 Release & Replay — QUEUED.** 验证版本固定查询、调度、旧 release 隔离和 FactorLab 冻结基线未变；之后结束 V3 P0，不进入 ETF NAV 或基金域。

### Frozen preceding milestone

`WEBUI_ETF_FACTORLAB_V1` 状态为 `PAUSED_AT_RESEARCH_DECISION`。P0、P1、P2 已完成；P3-A 保留批次 `c47d9a1c-2e25-4c3c-9759-92e073aa04ed`，尚未冻结代表因子且未访问 holdout；P3-B 为 `BLOCKED_DATA_IDENTITY`。DataHub V3 不得修改该批次成员、配置、缓存、产物或 holdout 状态。

### Prior acceptance retained

G0 已通过：固定 release 与两个 commit，检查 SDK 本地契约、实际 schema、原始资料和精确字段依赖；提交 Alpha101/ETF gap_plan 和最小实施计划。详细结果见 [G0 审计报告](acceptance/alpha101-etf/g0_inventory_report.md)。接口签名通过不代表网络健康。

G1 已通过 Alpha RAW 输入范围：固定原始量价、明确交易状态和历史总市值候选均已按候选→质量→固定版本回放发布。公司行为完整性属于 G3 账户门禁；行业三层映射只阻塞 18 条行业公式。验收见 [G1 报告](acceptance/alpha101-etf/g1_completion_report.md)。

G2 已通过 ETF_RAW 研究包：10 只 ETF 的固定主数据和原始日线由补充版本提供，Provider 与既有
BulletTrade 引擎已在固定版本上完成实际成交的月度轮动回放。完整证据见
[G2 Provider 回放记录](acceptance/alpha101-etf/g2_etf_provider_raw_replay.md)。公司行为仅样本覆盖、
历史规则/状态不完整，故 `ETF_HFQ_RESEARCH` 与严格账户仍保持关闭；该限制不阻塞 ETF_RAW 研究。

当前 G3：完成 Alpha101 与 ETF 的研究/会计/PIT 门禁，明确原始价研究、复权研究和严格账户的
输入、评价与可执行范围；行业多层与市值从已存原始资料重解析，不新增外部采集。
行业多层已在 `R9c1b6c13965dc457` 从归档申万原始文件重解析；其公开时间未知，严格 PIT
门禁不因此解除。

G3 已通过：Alpha101 三种模式与 ETF_RAW/严格账户资格已在固定 release 上明确记录，三级行业
输入已重解析发布，DataHub overview 已展示资格。复权、PIT 严格和账户级缺口均保持 BLOCKED。

G4 已通过：固定版本重复回放同 hash、旧版回放与隔离、缺失 release 失败、ETF 复权门禁和既有页面资格展示均已验证。完整矩阵见 [G4 最终验收](acceptance/alpha101-etf/g4_final_acceptance.md)。

## Queued Goals

P0 已完成：新实验使用 PostgreSQL 不可变 UUID，旧 JSON 存证只读兼容；release 从页面、API、Worker、Snapshot 到实验存证贯通，未知或缺失历史版本不会回退为 latest。P1 已完成：ETF_RAW 五模板经实际依赖预检后由实验组串行提交，费用由 BulletTrade 原生处理，权重信号、生效、目标及实际执行产物可追踪。P2 已完成：82 个量价因子支持固定静态池、逐因子 Parquet 产物、计算／评价双缓存、研究／验证分段评价；保留段默认关闭。

当前 P3 分为独立子项，不相互阻塞：

- **P3-A 因子精简：`AWAITING_RESEARCHER_SELECTION`。**相关性和完全链接聚类只读取研究／验证段；代表选择表并列验证 Rank IC、逐日／逐月正向比例、有效日期、平均横截面覆盖、最高分位换手与公式窗口／字段数。代表选择理由必填、冻结不可改写和保留段访问门禁均有自动化回归。固定五因子重复批次已验证跨批次计算／评价缓存和内容指纹一致；v3 选择证据批次 `c47d9a1c-2e25-4c3c-9759-92e073aa04ed` 已完成但未冻结或访问保留段。待研究者在网页选择代表因子并填写理由后冻结，方可首次访问保留段；这项研究判断不由系统自动作出。
- **P3-B 五行业 ETF 池：`BLOCKED_DATA_IDENTITY`。**行业定义及选择规则已经冻结，但当前本地主数据不能验证金融、消费、医药、科技、周期五类候选的跟踪指数身份，因此五类均如实 BLOCKED。现有 ETF_RAW 工作台继续可用；不为解除该子项重新建设基金数据库，只在正式开展行业轮动时按已冻结规则补充被选候选的身份、上市日期和日线。

验收见 [FactorLab 缓存与指纹](acceptance/webui-etf-factorlab/factorlab-cache-and-fingerprint.md)、[ETF 模板依赖预检](acceptance/webui-etf-factorlab/etf-template-dependency-preflight.md) 和 [行业 ETF 身份资格](acceptance/webui-etf-factorlab/industry-etf-eligibility.md)。


## Previous milestone

DataHub V2 COMPLETE；完整验收保留于 [历史 Active Phase](acceptance/datahub-v2/active-phase-completed.md)。
