# ETF 实验组持久化验收

固定 release `R9c1b6c13965dc457` 的实验组 `b7cd818e-bd9a-442c-878d-e953c8f59dc8` 使用 2021-01-04 至 2021-01-08 的等权模板。

组配置记录预检为可提交，并关联子运行 `run_3fb3e7d89b564208975ee7c27a7ffaca`。PostgreSQL 中子运行状态为 `SUCCESS`，配置保留该 release、基础/补充 commit、ETF_RAW 口径和生成报告路径。该短窗口验证组到子运行的持久化和串行执行链路；不是五模板完整窗口策略比较。
