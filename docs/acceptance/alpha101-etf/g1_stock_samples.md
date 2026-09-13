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

## 长区间状态补丁

同一计划的 298 只证券、2023-06-12 至 2026-09-01（每只 783 个交易日）已在一个
BaoStock 串行会话中取得。276 只证券的所有价格字段完整；另有 22 只在停牌/异常
窗口缺少 OHLCV 或成交额。采集器将这两种资格拆开：22 只的价格候选保持
`MISSING_OHLCV_OR_AMOUNT`，但其有效二元交易状态由持久原始响应离线重解析，未做
重复网络请求。

交易状态域共 233,334 行，发布前通过二元值、原始哈希、基础表零重叠和补充表零冲突
检查，已发布为 release `R3a6b9f500586cff5`、补充 commit
`k2qmvs43chnb1f1p7s6iffpgsej8ece2`。离线固定版本回读的
`000009.SZ`、`300001.SZ`、`600004.SH`、`689009.SH` 各为 783 行，
`688088.SH` 为其本批覆盖的 13 行；298 个持久原始哈希全部可读，网络调用为零。

价格质量门禁未放宽：`689009.SH` 有 480 个 BaoStock 价格键不在 R22 基础行情表；
另外 6 个 2024-01-08 成交额差异超过基础表当前 1 元显示精度。因此这些价格候选均
未发布，只有独立通过资格的交易状态进入本 release。

随后完成另一项 43 只证券、2023-06-12 至 2024-06-28 的精确状态任务（10,922 行）。
首次会话在 24 个完成分片后收到 BaoStock 网络接收错误；journal 保留 19 个
PENDING 分片，新的单会话仅重试这些分片并全部完成。发布门禁再次确认零基础重叠、
零补充冲突，生成 release `R7c90e0dc0cd2a127`、补充 commit
`1b91184gg3kehtp4jj3l1tvq611p7dfn`。该异常与重试记录保留在对应 staging journal。
固定版本离线回读 `000089.SZ`、`300257.SZ`、`688690.SH` 均为 254 行，43 个原始哈希
全部可读，网络调用为零。

第三、第四个短期任务分别为 43 只证券（2023-06-12 至 2023-12-29，5,891 行）和
42 只证券（2023-06-12 至 2024-12-31，15,918 行）。两批都通过相同的独立状态门禁，
分别发布为 `R68e2ed080184ea84` / `jubjtlgni5t28mgr8unk4ms05a4uok3c` 与
`R33d3b4a607d512c0` / `0fuh8h607nin12hbe6ib7l7mmsc7i5jr`。截至该节点，G1 已新增
266,572 条 `PARTIAL` 交易状态记录；每一补丁均限定其精确证券和交易日范围。

第五批为 34 只证券、2023-06-12 至 2025-12-31 的 21,148 行状态，发布为
`Rd474d5a53ad26532` / `p84e4cmeen7kr6ne7uucfmru16m1b6i4`。截至这一固定版本，
本轮已新增 287,720 条独立通过门禁的 `PARTIAL` 状态记录。

## 基础价格缺口样本

`000039.SZ` 在 2020-08-19 至 2020-08-25 的 5 个交易日是 G0 识别出的完整
OHLCV/金额缺口。固定 R22 基础表在这 5 个键上为零行；BaoStock 的单会话原始响应
`cafecac9deb77904437be7af985c004f8a8e8206279e3dbc9efd2419e54fb22d` 返回了 5 条
原始候选及明确交易状态。该窗口为停牌日，OHLC 保留、成交量与成交额为零，未由零
成交量推断状态。

此前该窗口被错误地视为“基础价格缺失”，并短暂进入 release
`R7ea863e0f6468694`。后续只读复核确认：虽然 `final_a_stock_eod_price` 对这 5 个
键为零行，固定基础 `bao_a_stock_eod_info` 已含完整原始 OHLCV/金额及
`adjclose`、`adjpreclose`、`adjfactor`。因此它属于基础 Raw Price Resolver 的
`FINAL_ROW_MISSING` 修复，不是外部补数；后继 current release 会撤回重复补充行，旧
release 仅保留审计与回放记录。

原始研究价格固定使用 `final → bao → external` 的顺序。`FINAL_ADJ` 与 `BAO_ADJ`
为不同价格模式，Bao 的复权字段不得填入 final 的 `adjclose` 缺口。

## 后续状态补丁

`000818.SZ` 在 2023-06-14 至 2025-06-30 的 494 个精确交易日中，价格键全部已
存在于固定基础行情表，因而没有价格补充写入。其 `tradestatus`/`is_st` 记录通过
二元值、原始哈希、基础状态表零重叠和既有补充零冲突检查后，已发布为 release
`R07d590ee202e9d20`、补充 Dolt commit `i5g5vqnsn41m0mv7gmeiqnvddbsfupje`。
该发布把状态数据集增加至 430,132 行、1,029 只证券，仍为 `PARTIAL`。

按 Raw Price Resolver 修订，current release 现为 `Rf5c0c823fd8084cf`、补充
commit `s5mtq2hr20jnlbdhhtco1810cjnuakdd`。它保留上述状态记录并从 current
补充库撤回 5 条与基础 Bao 原始价格重复的行；旧 release 不删除，仍可按其固定
commit 回放。

第六个状态任务覆盖 28 只证券、2023-06-14 至 2026-09-01 的 21,868 行，发布为
`R54f4889ece48b8ce` / `h15d4bij7r6ag36cjmtmjfliski4uvpa`。发布前二元状态、基础
重叠和既有补充冲突检查均通过。

## 巨潮实施公告

对 `600519` 做了一次 Cninfo 历史分红接口烟测。HTTP 200 原始响应的 SHA-256 为
`3afdfe3924e2c058e1eb4a6e3fa7d533303d3a82a5b30e76a685ff6e46d2e5ec`，解析出 31 条
实施公告候选。响应和 journal 位于
`/data/quantradar_data/staging/alpha-etf/g1-stock-events/`。

解析器保留实施公告日、登记日、除权日、派息日、股份到账日、每十股现金/送股/
转增和方案文本；缺失送股或转增比例不会补为零，因此对应的 `share_multiplier`
保持未知。报告期如“2025年报”按文本保存，不误作发布日期。候选的历史可得时间
仍未取得证据，故均为 `PARTIAL` PIT 且不可直接进入账户账务。

## Alpha #56 历史总市值候选发布

从 G0 固定原始目录的 997 份 Eastmoney
`RPT_VALUEANALYSIS_DET` 快照重新解析并逐份 SHA-256 校验，产生 1,933,230 条
`total_market_cap_cny` 记录，覆盖 997 只证券、2018-01-02 至 2026-09-11。候选
staging SHA-256 为 `20b76bd934f94d479fb949e105e1664250c05b068c7d87fce2f39fa0a6693076`；
流通市值字段被显式禁止作为替代。

这些记录已发布为 current release `Rb799aeb65657bf8d`，补充 Dolt commit
`2sg7kcf38n2svnet409ove3qpl91rc8c`。固定 commit 验证显示行数 1,933,230、证券数
997、负市值 0；`000006.SZ` / 2018-01-02 的总市值为 13,297,451,203.1 元。该数据集
具有 `CANDIDATE_NOT_PUBLISHED` 资格与 `PARTIAL` PIT 状态：它可作为 Alpha #56 的
总市值候选输入，不能证明历史时点可得性，也不能用于严格 PIT 评价。
