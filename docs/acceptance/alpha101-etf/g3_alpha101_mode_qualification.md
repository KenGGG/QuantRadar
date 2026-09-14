# G3 Alpha101 模式资格

依赖矩阵共有 101 条：82 条量价、1 条总市值（#56）、18 条行业中性化。以下是固定 release
`R9c1b6c13965dc457` 的输入资格，而不是收益表现或严格 WorldQuant 复刻声明。

| 模式 | READY | PARTIAL | BLOCKED | 结论 |
| --- | ---: | ---: | ---: | --- |
| `ALPHA101_RAW_ENGINEERING` | 82 | 19 | 0 | 82 条量价可用原始 OHLCV/amount 计算；#56 总市值与 18 条行业输入均只具 PARTIAL 时点资格。 |
| `ALPHA101_ADJ_RESEARCH` | 0 | 0 | 101 | 未发布一条跨来源审计的统一 A 股调整序列。 |
| `ALPHA101_PIT_STRICT` | 0 | 0 | 101 | 历史指数池、行业公开时间、财务可得时间及严格市场状态未完整合格。 |

行业 18 条现在有确定性的一级、二级、三级代码输入，不再因层级丢失而阻断；但它们仍是
`PARTIAL`，因为归档申万文件只含生效日与更新日，不含可验证的历史公开时间。#56 使用已发布
`qr_market_cap_daily.total_market_cap_cny`，也是 `PARTIAL`，因为东财历史快照不证明当日盘中/收盘前可得性。

因此“已有 Alpha101 原始公式能力”在本项目中称为 `ALPHA101_RAW_ENGINEERING`，不称作严格的
WorldQuant 101 复现。
