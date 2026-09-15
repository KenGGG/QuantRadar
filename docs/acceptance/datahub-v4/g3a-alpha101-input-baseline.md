# G3-A Alpha101 输入基线

审计固定 release `Rb9b7f3acc2fdab9c`，基础 commit
`0o6tgnmq5vabt3orqrk8rhqptniae26l`，补充 commit
`6gbkv4cik3ena0eh87p8ktmb6n0m4d86`。

## 历史总市值

`qr_market_cap_daily` 有 1,933,230 条事实，覆盖 997 只证券与
2018-01-02 至 2026-09-11。每条记录来自归档
`eastmoney:RPT_VALUEANALYSIS_DET` 的 `总市值` 字段；发布校验禁止
`float_market_cap` 替代。它可为 Alpha #56 提供真实样本，但不构成全市场
或 2018 年前覆盖声明。

## 申万历史归属与字典

`qr_sw_industry_history` 有 12,536 个历史区间、5,568 只证券，日期从
1990-01-01 到 2026-08-28。归档原件
`5cad0f27751a52c2849e4215068b72cfe95b48aca8b8c5679daa981cd5c13b53`
的工作簿只有“股票代码、计入日期、行业代码、更新日期”四列；不含行业名称、
父子关系或分类版本。现有 553 个六位代码及其前缀不能单独证明历史层级字典。

一次官方来源验证指向申万宏源 2021 分类标准说明 PDF
`https://wxweb.swsresearch.com/swsreport/2021_08/328340.pdf`；下载在
2026-09-15 返回 HTTP 403，未被伪造为成功原始证据。搜索结果可确认 2021
版本在 2021-07-30 推出，但不能补足旧版及全部代码—名称—父子关系映射。

因此当前 G3-A 资格为：

| 输入 | Coverage / Evidence | G4 用途 |
| --- | --- | --- |
| `cap` | 997 只、2018 起、归档总市值 | #56 可做真实样本 smoke test |
| `sector` | 历史证券归属代码存在；字典不足 | `BLOCKED_INPUT` |
| `industry` | 历史证券归属代码存在；字典不足 | `BLOCKED_INPUT` |
| `subindustry` | 历史证券归属代码存在；字典不足 | `BLOCKED_INPUT` |

该台账是来源限制证据，不以代码前缀或当前成分伪造历史字典。G3-A 保持
`IN_PROGRESS`，后续将把这一资格显式接入统一 Provider/FactorLab 预检。
