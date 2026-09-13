# G2 ETF 分红配送公告目录发布

以冻结的 10 只 ETF 为范围，通过按基金请求的 Eastmoney 分红配送公告目录获得真实公告
标题、公布日期与报告 ID。发布为 release `R824955e01387904d`、supplemental commit
`ogjmhhca673blf5m6eo7qpoi0rd15opi`，表 `qr_etf_event_announcement` 有 102 条记录、
9 只证券。

`510300.SH` 的固定版本读回包含 14 条目录记录，最早为 2012-12-12 的收益分配公告。
`159903.SZ` 的请求返回空目录；这保留为 `SOURCE_EMPTY_NOT_EVENT_ABSENCE_PROOF`，
不标记为“没有分红或拆分”。

本表资格为 `ANNOUNCEMENT_DIRECTORY_ONLY`：公布日期是可用的事件公开时间证据，但公告
目录不含现金金额、登记日、除息日、支付日或拆分比例。这些字段保持未知，不能进入账户
总回报、复权或严格 PIT 轮动计算。
