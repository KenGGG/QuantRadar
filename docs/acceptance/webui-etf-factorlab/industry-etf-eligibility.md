# 行业 ETF 身份资格验收

日期：2026-09-14

在固定本地 release `R9c1b6c13965dc457` 上只读查询 `qr_etf_master`。该 release 有 10 条 ETF 主数据，但没有任何一条记录的 `tracking_index` 能匹配五类已冻结的宽行业定义。

| 类别 | 定义 | 结果 |
| --- | --- | --- |
| 金融 | 银行与非银金融 | BLOCKED |
| 消费 | 主要消费 | BLOCKED |
| 医药 | 医药卫生 | BLOCKED |
| 科技 | 信息技术 | BLOCKED |
| 周期 | 原材料 | BLOCKED |

系统没有按 ETF 名称推断类别，也没有以宽基替换行业 ETF。后续只有经本地身份资料证明并冻结跟踪指数身份的 ETF 才能进入 P1 的模板编排。
