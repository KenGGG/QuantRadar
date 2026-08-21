# Kronos Goal 0 价格语义审计

- 价格样本：30；通过：30；失败：0
- 价格覆盖：1990-12-19 ～ 2026-08-18
- 价格语义门禁：PASS

## 唯一价格契约

- `fq=none`：`final_a_stock_eod_price` 原始 OHLC。
- `fq=post/hfq`：原始 OHLC × (`adjclose / close`)。
- `fq=pre/qfq`：原始 OHLC × 当日因子 / 显式参考日因子。
- Kronos 后续输入必须使用 `pre_factor_ref_date=signal_date`。
- `volume` 与 `amount` 不随价格复权。
- BulletTrade 成交与账户估值使用原始价；连续研究特征使用显式参考日的 qfq。

## 已知限制

- 公司行为表不存在，`preclose/adjfactor` 只能作为事件代理证据。
- ST、tradestatus、涨跌停及股票主数据的独立覆盖以前沿报告为准。
- 审计完成不等于正式回测或实盘数据门禁通过。
