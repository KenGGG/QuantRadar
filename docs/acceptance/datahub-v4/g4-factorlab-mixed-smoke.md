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

第二个固定 release 批次 `078298a5-2627-4797-b0e9-ee45ec5d1925` 验证
行业层级特有的两个公式：#48 为 `BLOCKED_INPUT`，缺
`indclass.subindustry`；#59 为 `BLOCKED_INPUT`，缺
`indclass.industry`。批次为 `BLOCKED` 且无错误字段。这些结果是预期的
来源限制结果，不是计算引擎失败。

在交易日预热和共享 Provider 改造后，批次
`95ba44c6-fbcc-4f9d-9d2c-61e8613f1771`（同一 release、证券池与窗口）记录
`calculation_start=2020-07-29`，并得到 #1 `COMPUTED`、#56 `COMPUTED`、#58
`BLOCKED_INPUT(indclass.sector)`。这证明预热取自固定 release 的交易日历，而不是日历日倒推。

随后批次 `08c49099-3bed-400d-b2d1-2306452e4b6f` 通过回测所用的固定
release Provider 读取 RAW 价格及已发布补丁，得到相同的 `PARTIAL_SUCCESS`
逐项结果。FactorLab 不再直接读取 `final_a_stock_eod_price`；基础行情、补丁和单位换算
使用与 Provider 相同的固定版本契约。
