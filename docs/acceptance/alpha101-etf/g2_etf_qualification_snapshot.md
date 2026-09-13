# G2 ETF 资格快照

固定范围为 10 只 ETF。当前 release `R8d403ef56426a33a` 已有全部 10 只的
`qr_etf_master` 和原始日线；主数据中的上市日均来自固定的官方原件，而非首个报价日。

真实公司行为仅有 `510300.SH` 的一条已核验现金分红样本：0.072 元/份，登记日
2021-01-15、除息日 2021-01-18、支付日 2021-01-21。交易规则记录为 0。

因此资格门禁结果为：

- `raw_price_research_ready = true`；
- `account_replay_ready = false`；
- `total_return_ready = false`；
- blockers：`EVENT_COVERAGE_INCOMPLETE`、`TRADING_RULES_INCOMPLETE`。

公告目录、当前基金档案、价格日线或单一样本不得消除上述 blocker。G2 继续以补足
全池真实事件与带生效期的交易规则为目标。
