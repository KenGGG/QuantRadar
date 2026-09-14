# Alpha101 与境内权益 ETF 数据补充 V2 最终验收

最终研究发布为 `R9c1b6c13965dc457`，基础 commit `uhdpedb4pr97ve80aq6nrabr66atsqtq`，补充 commit `r4t6rm3fdtb06rqpk0bmbtp2hn638a5r`。基础 Dolt 未写入；新增事实均在补充 Dolt。

| 目标 | 状态 | 证据与范围 |
| --- | --- | --- |
| ETF_RAW 日线与轮动 | PASS（研究） | 10 只 ETF 固定原始 OHLC/股/元，既有 BulletTrade 实际成交回放通过。 |
| ETF 公司行为/交易规则 | BLOCKED（严格账户） | 7 只 ETF 的 8 条事件样本，规则为 `EXCHANGE_RULE_PARTIAL`。 |
| Alpha101 原始工程模式 | READY 82 / PARTIAL 19 | 82 条量价；#56 与 18 条行业公式为 PARTIAL。 |
| Alpha101 调整价/PIT 严格模式 | BLOCKED 101 / 101 | 未发布统一调整序列；指数池、公开时间与财务可得时间未达严格 PIT。 |
| 行业三级 | PARTIAL | 归档申万 Excel 重解析为 553 个三级码；公开时间未知。 |
| 市值 #56 | PARTIAL | 已存 Eastmoney 原始载荷含总市值；不能证明历史时点可得。 |
| 现有页面展示 | PASS | `/api/datahub/overview` 展示 ETF/Alpha 资格和数据源。 |

固定 release 的 ETF_RAW 回放两次得到相同结果指纹：
`0020bceca29b4eba91dac37a58bb6e11ac570715ec2fb120ae7aa0802aa11fc`。旧 release
`Raa7aa73162640eb9` 也可回放，并保留旧一级行业码，证明版本隔离。

门禁故障验证：未知 release 明确失败，ETF `hfq/qfq` 明确拒绝，不存在联网回退或将原始价冒充复权价。相关单元测试共 42 项通过。
