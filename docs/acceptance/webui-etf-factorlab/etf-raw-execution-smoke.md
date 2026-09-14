# ETF 研究执行冒烟

固定数据版本：`R9c1b6c13965dc457`，基础 commit `uhdpedb4pr97ve80aq6nrabr66atsqtq`，补充 commit `r4t6rm3fdtb06rqpk0bmbtp2hn638a5r`。

2026-09-14 以 ETF_RAW 定期等权模板执行 2021-01-04 至 2021-01-08 的真实 BulletTrade 回放：10 个 ETF 均产生开仓成交，运行产生交易、持仓、日记录、指标和 HTML 报告。结果指纹为：

`ba9b133c63503d8932016c1070306b6cb20d5ea1b832086bfbe9360a1f71267c`

策略生成代码固定 `current_bar_fq='none'`，基金订单使用 BulletTrade `OrderCost`（买卖万三、最低 5 元、印花税 0）和原生 `PriceRelatedSlippage`。该窗口仅验证执行链路，不用于策略收益结论。

同一 release 的 2021-01-04 至 2021-03-31 预检显示：等权没有缺失依赖；其余四模板仅因 `159915.SZ` 在 2021-02-08 缺少收盘价而阻塞对应调仓点。该缺口没有阻塞等权模板。
