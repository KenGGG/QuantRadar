# G1 验收

日期：2026-10-09；状态：PASSED_WITH_RECORDED_DATA_LIMITATIONS。

- 独立 SQLite WAL、不可变策略修订与任务输入、FIFO 单任务、合法状态转换已实现。
- V2 API、独立模拟运行进程、日志偏移、产物校验登记、仅登记产物下载、原生报告均接通；不导入旧 DataHub。
- 10 项定向测试通过：交易隔离、SQLite、API、PID 重用保护、重启不重跑、完成文件恢复与校验。
- `npm.cmd run build:v2 --prefix frontend` 通过；Monaco 主包约5MB，产生体积警告，不影响本地验收。
- 独立 headless Edge 验证三页、保存修订、网页保存并回测、日志报告、恢复代码参数、大 QMT 健康及日线 OHLCVM 预览，无页面异常。见 browser-smoke.json、browser-run.json 及截图。
- 样本：600519.XSHG、000300.XSHG 基准、2026-09-01 至04、500000初始资金。API 与直接运行器 trades.csv、daily_positions.csv、daily_records.csv 和 metrics 内指标精确相同，见 live-smoke-parity.json。仅为同日普通 QMT 读取证明，冻结复现留待 G2。

原生 0.10.0 构造 benchmark 参数未使用，V2 通过生成的 bootstrap 调用公开 set_benchmark 应用网页默认，策略声明优先；原始策略冻结保存。大 QMT 历史 high_limit/low_limit 不支持：仅对原生 current-data 固定字段请求省略这两列，保留引擎既有估算规则；不伪造 QMT 涨跌停数据。精确历史 ST/上市限制尚不支持，记录在 effective_config.json。

缺 snapshot_selenium 的原生日历 PNG 为可选输出，日历 HTML 已生成。现有底层 Gateway 仍开放交易；V2 专用服务只提供 data，所有实测均为查询与模拟回测，没有真实交易调用。
