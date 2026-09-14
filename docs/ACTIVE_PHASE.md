# QuantRadar Active Phase

**Milestone:** `WEBUI_ETF_FACTORLAB_V1`
**Active Goal:** `WEBUI_P3_FACTOR_SELECTION_AND_INDUSTRY_ETF`
**Status:** IN_PROGRESS

## Scope

在既有双 Dolt、Provider、BulletTrade、Worker 和 WebUI 上交付 ETF 研究与 Alpha101 FactorLab。先完成不可变实验身份与固定 release 贯通，再分别交付 ETF 实验组、FactorLab 计算评价，以及行业 ETF 池和因子精简。
基础 Dolt 只读；不新增第三市场事实库，不在回测中联网或静默 fallback。ETF_RAW、调整价与严格 PIT/账户资格继续独立显示。

## Acceptance

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

- **P3-A 因子精简：`AWAITING_RESEARCHER_SELECTION`。**相关性和完全链接聚类只读取研究／验证段；代表选择表并列验证 Rank IC、逐日／逐月正向比例、有效日期、平均横截面覆盖、最高分位换手与公式窗口／字段数。代表选择理由必填、冻结不可改写和保留段访问门禁均有自动化回归。固定五因子重复批次已验证跨批次计算／评价缓存和内容指纹一致。待研究者在网页选择代表因子并填写理由后冻结，方可首次访问保留段；这项研究判断不由系统自动作出。
- **P3-B 五行业 ETF 池：`BLOCKED_DATA_IDENTITY`。**行业定义及选择规则已经冻结，但当前本地主数据不能验证金融、消费、医药、科技、周期五类候选的跟踪指数身份，因此五类均如实 BLOCKED。现有 ETF_RAW 工作台继续可用；不为解除该子项重新建设基金数据库，只在正式开展行业轮动时按已冻结规则补充被选候选的身份、上市日期和日线。

验收见 [FactorLab 缓存与指纹](acceptance/webui-etf-factorlab/factorlab-cache-and-fingerprint.md)、[ETF 模板依赖预检](acceptance/webui-etf-factorlab/etf-template-dependency-preflight.md) 和 [行业 ETF 身份资格](acceptance/webui-etf-factorlab/industry-etf-eligibility.md)。


## Previous milestone

DataHub V2 COMPLETE；完整验收保留于 [历史 Active Phase](acceptance/datahub-v2/active-phase-completed.md)。
