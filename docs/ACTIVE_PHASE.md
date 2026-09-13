# QuantRadar Active Phase

**Milestone:** `DATAHUB_ALPHA101_ETF_REQUIRED_DATA_V2`
**Active Goal:** `ALPHA_ETF_G2_ETF_PACKAGE`
**Status:** IN_PROGRESS

## Scope

用户于 2026-09-13 明确要求执行附件 V1/V2。以 [V2](superpowers/specs/2026-09-13-alpha101-etf-v2.md) 为接口修订依据，保留 [V1](superpowers/specs/2026-09-13-alpha101-etf-v1.md) G0—G4 验收。五份相同粘贴说明是任务背景，示例参数和健康推测均须核验。
沿用 main、双 Dolt、Provider、Governor、coordinator、journal、candidate 和既有页面。基础只读，不新增 Tushare 在线采集；无第三事实库；回测禁联网和静默 fallback。旧版本可回放。196 FAILED/123 未验证分母保留。

## Acceptance

G0 已通过：固定 release 与两个 commit，检查 SDK 本地契约、实际 schema、原始资料和精确字段依赖；提交 Alpha101/ETF gap_plan 和最小实施计划。详细结果见 [G0 审计报告](acceptance/alpha101-etf/g0_inventory_report.md)。接口签名通过不代表网络健康。

G1 已通过 Alpha RAW 输入范围：固定原始量价、明确交易状态和历史总市值候选均已按候选→质量→固定版本回放发布。公司行为完整性属于 G3 账户门禁；行业三层映射只阻塞 18 条行业公式。验收见 [G1 报告](acceptance/alpha101-etf/g1_completion_report.md)。

当前 G2：冻结 10 只境内权益 ETF 的身份范围，逐项补齐非复权日线、真实分红拆分、必要主数据及交易规则；每个候选数据集依次小样本、质量验收、固定版本回放后才发布。未具备外部证据的范围保持 UNKNOWN/BLOCKED。

## Queued Goals

1. `ALPHA_ETF_G3_RESEARCH_AND_ACCOUNTING`：公式/评价/执行/PIT 四级门禁，输入及账户对账和轮动。
2. `ALPHA_ETF_G4_RELEASE_AND_REPLAY`：逐项发布、断网同 hash、故障注入、旧版回放和现有数据页资格展示；市值/行业只阻塞依赖项。

## Previous milestone

DataHub V2 COMPLETE；完整验收保留于 [历史 Active Phase](acceptance/datahub-v2/active-phase-completed.md)。
