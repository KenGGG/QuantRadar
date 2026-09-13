# G2 ETF 资格快照

固定范围为 10 只 ETF。当前 release `Ref5817b79f851874` 已有全部 10 只的
`qr_etf_master` 和原始日线；主数据中的上市日均来自固定的官方原件，而非首个报价日。

真实公司行为有六只 ETF 的已核验事件样本：`510300.SH` 现金分红 0.072 元/份，
`510050.SH` 0.037 元/份，`510880.SH` 0.05 元/份、`159901.SZ` 0.085 元/份；
`159919.SZ` 0.0661 元/份、`510500.SH` 0.087 元/份；前述现金事件均含登记、
除息和支付日。`510500.SH` 另有 2022-08-26 份额拆分，倍率 1.14539。
交易规则记录为 0。

因此资格门禁结果为：

- `raw_price_research_ready = true`；
- `account_replay_ready = false`；
- `total_return_ready = false`；
- blockers：`EVENT_COVERAGE_INCOMPLETE`、`TRADING_RULES_INCOMPLETE`。

公告目录、当前基金档案、价格日线或单一样本不得消除上述 blocker。G2 继续以补足
全池真实事件与带生效期的交易规则为目标。
