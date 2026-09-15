# G4 FactorLab 混合输入烟测

批次 `a1402a37-1674-4c54-b548-e010bd0d6ba3` 固定读取 release
`Rb9b7f3acc2fdab9c`（base `0o6tgnmq5vabt3orqrk8rhqptniae26l`，
supplemental `6gbkv4cik3ena0eh87p8ktmb6n0m4d86`）。它使用 25 只具有
2020—2021 历史总市值覆盖的显式证券池、RAW 价格、`adv_basis="amount"`
和既有下一交易时点标签定义；未访问网络或 holdout。

| Alpha | 依赖 | 逐项状态 | 证据 |
| --- | --- | --- | --- |
| #1 | 基础量价 / returns | `COMPUTED` | 固定 release 量价链路可用 |
| #56 | `returns` + `cap` | `COMPUTED` | 归档总市值输入可用 |
| #58 | `indclass.sector` | `BLOCKED_INPUT` | 缺经验证版本化申万字典 |

批次最终状态为 `PARTIAL_SUCCESS`，没有 `FAILED_ENGINE`。这证明数据阻塞
不会再被误报为工程失败，且独立公式可继续执行。行业阻塞的来源与范围见
[G3-A 输入基线](g3a-alpha101-input-baseline.md)。
