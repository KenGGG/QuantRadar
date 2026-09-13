# G1 A 股 Alpha101 输入验收

固定 current release 为 `Rb799aeb65657bf8d`，基础 Dolt commit 为
`uhdpedb4pr97ve80aq6nrabr66atsqtq`，补充 Dolt commit 为
`2sg7kcf38n2svnet409ove3qpl91rc8c`。

## 通过范围

- `ALPHA101_RAW` 使用 `final_a_stock_eod_price → bao_a_stock_eod_info →`
  受控外部修补的固定优先级。价格、成交量和成交额统一在读取边界转换为股和元；
  Bao 仅修复 final 缺失的原始行，绝不填补 final 复权锚点。
- `trade_status_daily` 已发布 430,132 行、1,029 只证券，作为明确的 `PARTIAL`
  状态候选；缺状态仍为未知，零成交量不推断停牌。
- `market_cap_daily` 已从 997 份 hash 校验的归档快照发布 1,933,230 条
  `total_market_cap_cny`。Alpha #56 在固定版本上的 3 证券、59 交易日探针有 51 个
  有效值。流通市值没有被替代使用。
- Alpha 的 82 条纯量价公式可以使用上述 RAW 输入；其结果仍须在 G3 按历史池、状态与
  时点门禁区分“可计算”和“可评价/可交易”。

## 不提升资格的限制

- 已捕获的股票实施公告候选缺少完整送转份额和历史可得时间；公司行为只作为 G3
  账户、总回报和复权验证门禁，按照 RAW 规则不阻塞 Alpha RAW。
- 历史市值为 `PARTIAL / CANDIDATE_NOT_PUBLISHED`，不能用于严格 PIT 评价。
- 申万表目前只有一个历史 `industry_code`；没有可靠的 sector/industry/subindustry
  三层映射。因此 18 条行业公式明确为 `BLOCKED_MISSING_LEVEL_MAPPING_AND_STRICT_PIT`，
  不能以一级行业复制填充。

这些限制只阻塞直接依赖它们的工作流，不阻塞 G2 的境内权益 ETF 价格型数据包。
