# G5 固定 release 离线 Alpha101 矩阵

批次 `07b6a40d-dd68-44bd-a210-74633530aa41` 在固定 release
`Rb9b7f3acc2fdab9c` 上执行。输入为 25 只显式证券、2020-09-01 至
2021-06-30、RAW 价格、`adv_basis="amount"`、一个交易日预测窗口；读取仅使用
本地发布的双 Dolt 版本，未访问网络或 holdout。

| 逐项结果 | 数量 |
| --- | ---: |
| `COMPUTED` | 71 |
| `FORMULA_EMPTY_VALID` | 12 |
| `BLOCKED_INPUT` | 18 |
| `FAILED_ENGINE` | 0 |

批次最终为 `PARTIAL_SUCCESS`。18 个阻塞项均缺经版本化验证的申万层级字段；这与
G3-A 的有限来源验证相符，未使用代码前缀伪造行业层级。

固定组合 #1/#56/#58 的前两项在同一 release 已真实计算；#58 依赖
`indclass.sector`，因此组合资格为 `BLOCKED_INPUT`。没有换因子、调参或访问旧
holdout。组合无法在当前来源限制下形成净值，是可复现的数据阻塞结论。
