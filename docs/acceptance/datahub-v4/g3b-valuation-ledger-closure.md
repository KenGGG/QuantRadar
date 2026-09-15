# G3-B 估值底账收口

固定 release `Rb9b7f3acc2fdab9c` 对应的持久 journal
`valuation_daily-mvp.json` 在 2026-09-15 的可复现计数如下：

| 状态 | 证券数 | 工程结论 |
| --- | ---: | --- |
| `COMPLETE` | 5,235 | 已保留发布与原始证据 |
| `FAILED` | 196 | `SYMBOL_DATA_ERROR`，AKShare `stock_value_em` 的稳定 `NoneType` 解析错误 |
| `NOT_COVERED` | 123 | 来源未提供覆盖证据 |
| `PENDING` | 345 | 证券主表增量，尚待单独审计 |

三个失败样本（`000022.SZ`、`000043.SZ`、`002504.SZ`）均重现同一
`TypeError: 'NoneType' object is not subscriptable`，没有出现 403、429、超时或
熔断信号。估值字段保持 `PE_TTM`、`PB_MRQ`、`PS_TTM`、`PCF_OCF_TTM`；负值和
合法空值保留，NCF 不替代 OCF。

本轮不为追求 100% 覆盖继续替换来源。每个未解决项仍保留缺口键、状态、错误类别和原始
journal 证据；G3-B 因而按“来源限制已工程处理”收口，且不影响 G4/G5 的 RAW Alpha101。
