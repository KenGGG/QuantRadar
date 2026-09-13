# G1 A 股受控样本

本文件记录候选数据集的小样本验证，不代表已发布的全历史数据，也不使任何
Alpha101 或回测路径获得严格 PIT 资格。

## BaoStock 日线与状态

2026-09-13 使用一个 BaoStock 登录会话，按已存 CSI500 快照在 2024-01-02
选取深市主板 `000009.SZ`、创业板 `300001.SZ`、沪市主板 `600004.SH`。每只
请求并严格验证 2024-01-02 至 2024-01-10 的 7 个交易日。

| 证券 | 行数 | 原始响应 SHA-256 |
| --- | ---: | --- |
| `000009.SZ` | 7 | `bc162a11bfc215db5c6c2fafb9a10b4e5a9080ceb22237d4586a7451597901be` |
| `300001.SZ` | 7 | `199dea48c884998143be2fbc8f0bcc2c2fead52b9f4fb592cd75b53084616c42` |
| `600004.SH` | 7 | `38d758bff049d4e2cf55612dd45339b7af75e0cc99e873c1b44ad88489ad7811` |

每份响应都使用 `a-stock-data@2012ce7cd0e75d379c5e6cbd3115514f300f3bc8`
适配器版本保存为 `SDK_RESPONSE_SNAPSHOT`，并验证完整 OHLC、成交量、成交额、
`tradestatus` 与 `isST`。标准化候选明确使用
`baostock-shares-yuan` 单位契约和原始价格；成交量未因任何价格调整而改变。
staging 目录：`/data/quantradar_data/staging/alpha-etf/g1-stock-daily-sample/`。

同一 21 条记录已同固定 R22 base commit
`uhdpedb4pr97ve80aq6nrabr66atsqtq` 的 `final_a_stock_eod_price` 对拍通过：
OHLC 相同，BaoStock 的成交量（股）和成交额（元）分别与基础表的手和千元契约
一致。基础表的显示精度为 0.01 手、0.001 千元，因此对拍仅容许 50 股和 1 元的
显示舍入界限；最终差异为零。机器可读报告为
`quality_reconciliation.json`。

## 首个交易状态补丁发布与回放

以该流程的下一批为范围，已采集 39 只股票在 2023-06-12 至 2023-06-30 的 507 条
日线/状态候选，并完成同一固定基础提交的价格与单位对拍（507 行、零差异）。所有
39 个原始响应已从 task staging 哈希校验后提升到持久
`/data/quantradar_data/raw-artifacts/`。

发布前门禁确认 507 条 `tradestatus`/`is_st` 均为二元值、原始哈希和合同字段完整、
与基础 `bao_a_stock_eod_info` 零重叠、与既有补充记录零冲突。补丁发布为 release
`R140e969c0739e918`，补充 Dolt commit 为
`lf1j4a47qectprtdbn5co1nftrbmcomo`；基础 commit 仍为
`uhdpedb4pr97ve80aq6nrabr66atsqtq`。

离线回读该 release 的三个跨市场样本均返回 13 条状态记录，39 个持久原始哈希全部
可读取；该验证的网络调用数为零。此补丁仅覆盖上述精确日期/证券范围，数据集和
release 仍标记 `PARTIAL`，不声明全市场状态或严格 PIT 完整。

## 巨潮实施公告

对 `600519` 做了一次 Cninfo 历史分红接口烟测。HTTP 200 原始响应的 SHA-256 为
`3afdfe3924e2c058e1eb4a6e3fa7d533303d3a82a5b30e76a685ff6e46d2e5ec`，解析出 31 条
实施公告候选。响应和 journal 位于
`/data/quantradar_data/staging/alpha-etf/g1-stock-events/`。

解析器保留实施公告日、登记日、除权日、派息日、股份到账日、每十股现金/送股/
转增和方案文本；缺失送股或转增比例不会补为零，因此对应的 `share_multiplier`
保持未知。报告期如“2025年报”按文本保存，不误作发布日期。候选的历史可得时间
仍未取得证据，故均为 `PARTIAL` PIT 且不可直接进入账户账务。
