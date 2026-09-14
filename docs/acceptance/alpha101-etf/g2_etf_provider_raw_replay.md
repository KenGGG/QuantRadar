# G2 ETF_RAW Provider 与既有引擎回放

固定发布版本：`Raa7aa73162640eb9`（补充库
`pdslpnia1j1a3oro4f2qp89e4tbt7889`）。本记录只使用该版本和本地原始资料；未进行任何网络采集。

## 已接入

`InvestmentDataProvider.get_price()` 现先以 `qr_etf_master` 识别已发布 ETF，再从同一固定版本的
`qr_etf_eod_price` 读取 `ETF_RAW`。`volume_shares` 映射为 `volume`（股），`amount_cny` 映射为
`money`（元），不会经过股票表的手/千元换算。已知未观测日期按交易日历重建为 `NaN`；没有
交易状态时 `paused` 保持未知。

实际读取 `2021-03-09` 至 `2021-03-11`：`510300.XSHG` 三日完整；
`159901.XSHE` 在 `2021-03-10` 为 `NaN`。该格的资格是 `UNKNOWN_OBSERVATION`，并非停牌判断。

ETF 主数据也已由 `qr_etf_master` 提供给 `get_security_info()`，使现有引擎可取得上市日期、交易所和基金名称。

## 原生引擎回放结果

用既有 `quantradar.backtest.run_backtest()` 和 BulletTrade 引擎执行了十只 ETF、每月一次、20 个交易日动量选第一名的最小策略：

| 项目 | 结果 |
| --- | --- |
| 区间 | 2021-01-04 至 2021-03-31 |
| 数据模式 | `ETF_RAW` |
| 交易日记录 | 58 |
| 成交 | 0 |
| 结果 | `BLOCKED_ENGINE_FQ_PRE_REQUEST` |

阻断并不在原始历史价：例如 `159915.XSHE` 于 `2021-01-04` 可直接读到 open、close、volume 与 money。
订单阶段的 `BacktestCurrentData` 固定以 `fq='pre'` 请求 current bar；ETF 没有已发布复权因子，Provider
按门禁拒绝该请求，因此引擎把该 bar 视为空并拒单。不能以 ETF_RAW 冒充前复权来绕过此门禁。

下一项最小工作是为现有引擎增加明确的 `ETF_RAW` current-bar 请求模式，保持 `ETF_HFQ_RESEARCH`
和严格账户关闭，且不新增引擎或 WebUI。

## 既有原始资料的二次核验

* Eastmoney `RPT_VALUEANALYSIS_DET` 的已有原始对象
  `5b000394ad7289bcb7b1c5bc190a5338be6dd678523beaaa29d089afd234813f` 含“总市值”列；样本有
  2,057 行且全部非空。因此 #56 的问题是现有标准化器未保留该列，不是本地原始载荷缺失。
* 申万原始 Excel 对象
  `5cad0f27751a52c2849e4215068b72cfe95b48aca8b8c5679daa981cd5c13b53` 有 12,909 行、553 个六位行业代码，
  并含“计入日期”“更新日期”。其中可得 38 个一级、194 个二级、553 个三级代码。当前
  `build_sw_level_one_intervals()` 将 `industry[:2] + '0000'` 写入发布表，造成层级丢失；原始资料可支持重解析，
  但当前发布的一级表尚不能用于 WorldQuant 的 sector/industry/subindustry 三层输入。
