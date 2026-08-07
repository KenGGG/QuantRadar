# JQData 数据源封装说明

本实现位于 `bullet_trade/data/providers/jqdata.py`，在 `DEFAULT_DATA_PROVIDER=jqdata`（默认值）或显式 `set_data_provider('jqdata')` 时启用。以下要点帮助理解适配逻辑与常见问题。

## 依赖与认证
- 依赖官方 `jqdatasdk`，并对 `get_price_engine` 打补丁以支持 `pre_factor_ref_date`。  
- 支持从 `.env` 或 CLI 参数读取 `JQDATA_USERNAME`/`PASSWORD`/`SERVER`/`PORT`，也可以通过 `set_data_provider('jqdata', username='xxx', password='xxx')` 覆盖。  
- `CacheManager` 默认读取 `DATA_CACHE_DIR/jqdatasdk`，可按需关闭或调整 TTL。

## 动态复权
- 当前真实价格模式 (`use_real_price=True`) 会将 `prefer_engine=True`、`pre_factor_ref_date=回测时点` 传递给 provider。  
- JQDataProvider 直接调用补丁后的 `get_price_engine`，由 SDK 负责在返回结果中使用指定的复权基准，因此无需额外缩放。

## 事件与数据结构
- 股票分红：来自 `finance.STK_XR_XD`，使用 `bonus_ratio_rmb`（现金）、`dividend_ratio`（每10股送股）、`transfer_ratio`（每10股转增）；若聚宽返回的是总股本字段则自动根据披露的基数折算。  
- 基金/ETF：使用 `finance.FUND_DIVIDEND`；货币/分级基金单独走 `finance.FUND_MF_DAILY_PROFIT`。  
- 返回统一字段：`security`、`date`、`security_type`、`scale_factor`、`bonus_pre_tax`、`per_base`。

## 可能遇到的问题
1. **权限或额度不足**：`jqdatasdk` 抛出 `PermissionError` 时，通常意味着账号未开通所请求的数据表，需要在聚宽后台申请。  
2. **自建缓存冲突**：若 `DATA_CACHE_DIR` 指向共享目录，请确保不会与其他应用复用同一路径。  
3. **Panel 格式兼容**：聚宽仍使用 `pd.Panel` 返回多标的行情，本封装会尝试调用 `to_frame()` 并转换为 MultiIndex DataFrame；如遇 `FutureWarning` 可忽略。  
4. **extreme 日期**：当 `start_date`/`end_date` 超出标的上市区间时，SDK 会返回空 DataFrame；框架会在日志层面提示“获取数据失败”，属预期表现。

如需扩展更多 JQData 能力，可直接在该 provider 内增加辅助方法，再通过 `bullet_trade.data.api.set_data_provider` 暴露。***
