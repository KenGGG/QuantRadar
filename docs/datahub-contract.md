# Local daily data contract

新发布版本的 `metadata.price_units = joinquant-shares-yuan-v2`。缺少该标记的历史 release 使用 legacy-v1 原样回放，不能把其原始成交量/成交额解释为新版单位。策略不选择目录。

| API / 字段 | 固定版本来源 | 类型、单位与转换 | 日期与缺口 |
|---|---|---|---|
| get_price / open, high, low, close | 基础 final_a_stock_eod_price | 日频浮点，元；none 原始价，pre/post 保持既有真实因子规则 | 查询交易日；缺记录为 NaN，不能宣称全范围完整 |
| get_price / volume | 同上 | 原表手 × 100 → 股；不随复权缩放 | 停牌/缺日不能靠填造成交量解决 |
| get_price / money, amount | 同上 amount | 原表千元 × 1000 → 元；money 是字段别名 | 同上 |
| get_extras / is_st, tradestatus | 基础 bao_a_stock_eod_info | 真实状态值；与行情有独立覆盖日期 | 缺数据显式 NaN，不能因行情更新宣称 ST 也更新 |
| get_fundamentals / valuation.code, pe_ratio, pb_ratio, ps_ratio | 补充 qr_valuation_daily / symbol, pe_ttm, pb_mrq, ps_ttm | 代码转为 XSHG/XSHE；比率为倍数，不做百分比缩放 | 必须明确股票池；缺行、必需字段空值、隔离项抛错；PIT_PARTIAL |
| SupplementalReader / pcf_ocf_ttm | 同上，获准 Eastmoney RPT_VALUEANALYSIS_DET | 经营现金流口径倍数；不是 NCF，未映射到未核验的 JQ pcf 字段 | 可得日期不完整，严格 PIT 不通过 |
| get_industry / sw_l1 | 补充 qr_sw_industry_history / industry_code | 申万一级代码；名称未提供 | 按 effective_from/effective_to 生效区间；缺失报错；历史可得时点 PARTIAL |
| lifecycle_as_of | 补充 qr_security_lifecycle | 仅当前获准基础名录来源；上市日不从行情首日推断 | list_date/delist_date 过滤；名录陈旧与历史可得限制独立保留 |

沪深股票代码在内部使用 SH/SZ 或 .SH/.SZ，API 使用 .XSHG/.XSHE；不宣称 ETF、北交所、全财务表或分钟线兼容。
同一次运行固定 base_commit、supplemental_commit、release_id 和单位版本。数据不足不切换未批准来源，不用下载成功的子集替代用户股票池。

单位依据：[Tushare 日线官方契约](https://tushare.pro/document/2?doc_id=27)。部署库的 12 个跨年份证券交易日样本与独立历史字段核对，以及另 15 个价格区间样本，见 `acceptance/datahub-remediation-2026-09-11/price-unit*.json`。
这验证了采样范围的转换关系，不等于对所有历史行或跨源估值准确性完成审计。
