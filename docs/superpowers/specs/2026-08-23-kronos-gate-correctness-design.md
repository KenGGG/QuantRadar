# Kronos 门禁正确性设计

## 范围

本次改动修复 PR #2 的四项验收阻塞问题，同时不恢复默认 Kronos 信号研究对旧
CSI300 PIT 的依赖。默认股票池仍为 `all_a_liquid`；CSI PIT 仍是一项独立的可选能力。

## 严格的全 A 股 PIT 输入资格

对于 `all_a_liquid`，候选股票在 signal date 当天必须有一条有效行情。候选查询因此
选择 `tradedate` 等于 signal date 的 A 股代码，而不是任何较早日期曾出现过的代码。
这样会把已经退市的证券，以及 signal date 当天没有行情的证券排除在当前横截面外。

共享市场日历定义标准输入窗口：以 signal date 为终点的最近 90 个开市日。只有当一只
股票返回的价格日期严格等于该标准序列，并且 OHLCVA 值通过现有的完整性与结构校验时，
它才具备资格。因此，Provider 用更早的 90 条观测值填补停牌缺口时，该股票会被排除。

`all_a_liquid` 的 signal date 枚举会把请求的结束日期截断至 `latest_price_date`。
若截断后没有市场日期，则返回空列表。直接构建输入时，也会拒绝晚于最新可用行情日期的
signal date。

## 能力门禁

`kronos_signal_research_ready` 继续表示可以进行基于 OHLC 的 Kronos 信号研究。
新增 `research_backtest_ready`，作为等价的仅研究级回测许可。

当最新交易可行性证据并非 `BLOCKED` 时，`realistic_backtest_ready` 可以为真，且其
fidelity 为 `PARTIAL`；它不是“达到正式质量”的声明。只有同时满足 Kronos 研究可用、
最新交易可行性证据为 `PASS`、公司行为证据可用时，`formal_backtest_ready` 才为真。
其中任一要求未满足时，它必须保持为 false。`real_assist_data_ready` 仍要求完整的最新
交易可行性证据。

## 可复现的审计缓存

数据审计写入器会将 Dolt 的 `data_commit` 记录到 `data_gate.json`。研究流水线仅在缓存
gate 可解析，且其 `data_commit` 与当前 SignalRun 的 Dolt HEAD 严格一致时才采用它。
缺失、格式损坏或过期的缓存会对 realistic、formal、real-assist 和 CSI PIT 能力给出
保守的 false 值。manifest 会记录是否使用了 commit 匹配的审计 gate。

## CI 隔离

每一个连接真实 `investment_data` 的测试（包括新的全 A 股 live test）都必须带有现有的
`requires_dolt` 标记。Dolt 不可达时，该标记的收集钩子会跳过测试，因此 GitHub Actions
只运行纯单元测试，不会尝试连接 `127.0.0.1:3307`。

## 测试与验收

单元测试覆盖：退市或 signal date 当日无行情的候选排除、未来结束日期截断、含停牌/缺日的
90 日窗口、直接传入未来 signal date 的拒绝、门禁语义，以及 commit 匹配、过期和缺失
审计缓存的处理。live 测试保留 `requires_dolt`，并在 CI 中跳过。完成条件为：定向 Kronos
单元测试、`make test`、前端构建全部通过，且分支推送后 GitHub Actions 变绿。
