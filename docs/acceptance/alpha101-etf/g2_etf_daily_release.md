# G2 ETF 原始日线候选发布

固定范围为 [etf_g2_scope.json](etf_g2_scope.json) 的 10 只境内权益 ETF。基础
`final_a_stock_eod_price` 对这些代码没有行，因而本数据集不覆盖或覆盖基础数据，而是
独立的 ETF 补充事实。

通过 Eastmoney ETF 原始 K 线端点，以 `fqt=0` 取得每只证券的一次连续历史响应；所有
响应由 Governor 归档并按 SHA-256 记录。每条记录通过 OHLC 和非负量额检查，且以
`amount / (close * volume)` 的量级验证“手/元”单位。成交额代表日内成交均价，允许
相对收盘价的合理偏差；它不会被误当作精确的 close×volume 恒等式。

发布结果：

- release：`R17ee5fdb458b481e`；supplemental commit：`ph83ecq6p895oeofsmdved3nen6vr6lq`；
- `qr_etf_eod_price`：38,117 行、10 只证券、原始不复权 OHLC、成交量（股）和成交额（元）；
- 首尾观测范围按证券分别记录在 staging；首个报价日不是上市日期证明；
- 候选 staging SHA-256：`7fee1d1b1b8f5a8a0edd01014de17f4399715866cb249cf918bfed88eb91cfed`；
- 资格为 `PARTIAL / CANDIDATE_NOT_PUBLISHED`。身份、真实分红拆分、交易规则和历史
  可得时间尚未验收，故本发布不能单独支持账户总回报或严格 PIT 轮动。

离线固定版本读回 `510300.SH` 和 `159919.SZ` 的 2024-01-02 至 2024-01-05 各为 4 行，
无网络请求。
