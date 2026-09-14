# G2 ETF 本地资料复用核验

本报告替代继续按年份扫描全基金事件目录的工作主线。仅读取固定 release
`Raa7aa73162640eb9`（base `uhdpedb4pr97ve80aq6nrabr66atsqtq`，supplemental
`pdslpnia1j1a3oro4f2qp89e4tbt7889`），未发出网络请求，未修改基础 Dolt。

研究区间为 2020-01-01 至 2026-08-31；范围是既有的十只境内权益 ETF。

| 标的 | 基础行情/复权/链接表 | 补充原始日线 | 研究窗口覆盖 | 当前用途资格 |
| --- | --- | --- | --- | --- |
| 510050.SH | 六张股票行情表及三张链接表均为 0 行 | raw OHLC、成交量额 | 1615/1615 交易日 | 原始价格信号候选 |
| 510180.SH | 同上 | 同上 | 1615/1615 | 原始价格信号候选 |
| 510300.SH | 同上 | 同上 | 1615/1615 | 原始价格信号候选 |
| 510500.SH | 同上 | 同上 | 1615/1615 | 原始价格信号候选 |
| 510880.SH | 同上 | 同上 | 1615/1615 | 原始价格信号候选 |
| 159901.SZ | 同上 | 同上 | 1614/1615，缺 2021-03-10 | 缺失观测待解释 |
| 159902.SZ | 同上 | 同上 | 1615/1615 | 原始价格信号候选 |
| 159903.SZ | 同上 | 同上 | 1615/1615 | 原始价格信号候选 |
| 159915.SZ | 同上 | 同上 | 1614/1615，缺 2021-02-08 | 缺失观测待解释 |
| 159919.SZ | 同上 | 同上 | 1615/1615 | 原始价格信号候选 |

“六张股票行情表”是 `final_a_stock_eod_price`、`bao_a_stock_eod_info`、
`ts_a_stock_eod_price`、`c_a_stock_eod_price`、`w_a_stock_eod_price` 与
`yahoo_a_stock_eod_price`；链接表是 `c_link_table`、`ts_link_table` 与
`yahoo_link_table`。基础 schema 虽有 `adjclose`、`adjpreclose`、`adjfactor`
与 `adj_ratio`，但目标 ETF 均无实际记录，不能把 A 股复权融合机制外推给 ETF。

补充库 `qr_etf_eod_price` 的所有记录是 `adjustment=raw`、
`unit_status=HAND_AND_CNY_QUALIFIED`，且 OHLC、成交量额均非空。它没有 ETF
复权价或复权因子；因此不能把这一日线称为总回报序列，也不能与基础库的 A 股 `adjclose`
拼接。当前 `InvestmentDataProvider` 的 ETF 能力仍是 `BLOCKED`：数据已经发布，
但尚未接入 Provider/策略路径。这是接入缺口，不是底层行情缺失。

主数据十只均有官方上市日。公司行为只有七只、八条 `SAMPLE_ONLY_NOT_POOL_COMPLETE`
事实；交易规则十只均只有 2026-07-06 起的 `EXCHANGE_RULE_PARTIAL` 记录，历史费用、
回转限制及特别状态为 `UNKNOWN`。它们不阻塞价格信号研究，但继续阻塞严格现金、份额和
到账日的账户回放。

下一步最小实现是将上述固定补充原始日线接入既有 Provider 的 ETF 分支，并以原始价格
明确标记一条固定版本的价格型轮动研究回放；不能静默省略两个缺失日期或把它们认定为停牌。
复权收益研究须先取得 ETF 复权口径的本地证据；严格账户回放仍须按实际持仓窗口补齐所需
事件与规则字段。任何外部补数请求都必须先指明证券、日期、字段和它解除的具体门禁。

## Alpha101 与行业结论

WorldQuant 101 尚未全部准备齐全：82 条纯量价公式可使用 `ALPHA101_RAW`，第 56 条
总市值输入为 `PARTIAL / CANDIDATE_NOT_PUBLISHED`，18 条行业公式被
`BLOCKED_MISSING_LEVEL_MAPPING_AND_STRICT_PIT` 阻塞。行业资料并非没有：固定补充库有
12,536 行、5,568 个证券的单层申万 `industry_code` 历史区间；但缺少可审计的
sector / industry / subindustry 三层历史映射与严格 PIT 可得时间，不能将一级码复制为三层。
