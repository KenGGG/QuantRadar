# QuantRadar2 G2 首版验收

验收日期：2026-10-09（Asia/Shanghai）；结论：**通过，G0 → G1 → G2 首版完成**。G3 未启动。

## 交付

SQLite schema2、策略修订/复制/归档/恢复、FIFO 独立回测进程、增量日志、原生报告、有限数据预览、冻结记录/离线回放。API/WebUI 为 127.0.0.1:7242，数据专用服务为 58621。只使用外部 BulletTrade 0.10.0 的原生引擎，不修改引擎或 QMT 安装文件，不接入旧 DataHub/数据库，不提供真实交易能力。

## 四组有限策略精确一致

[原始证据](strategy-suite.json) 记录源码 hash、参数、任务 ID、冻结请求数、费用和产物比较。每组依次执行真实 QMT 记录、API 离线回放、直接运行器离线回放。直接回放配置指向不存在的线上配置，验证无回源依赖。

| 场景 | 标的/窗口 | 冻结请求 | 模拟成交 | 原生费用 |
|---|---|---:|---:|---:|
| 买入持有 | 600519；2026-09-01 至 09-04 | 24 | 1 | 38.90 |
| 日频双均线 | 510300；2026-09-01 至 09-30 | 127 | 7 | 486.64 |
| 月度动量 | 固定 510300/510500 池；2026-08-03 至 09-30 | 188 | 3 | 362.49 |
| 分钟回调/交易 | 510300；2026-09-29 至 09-30 | 257 | 2 | 10.00 |

初始资金均为 500000，基准 000300.XSHG，复权参考日期 2026-10-09。原生 trades.csv、daily_positions.csv、daily_records.csv 逐项精确一致；核心 metrics 精确一致，只排除生成时间/耗时等非经济元数据，不采用放宽误差阈值。

夹具为 examples/v2 下四个策略；冻结响应包分别为 [buy_hold](buy_hold-frozen-data.zip)、[daily_ma](daily_ma-frozen-data.zip)、[etf_monthly_momentum](etf_monthly_momentum-frozen-data.zip)、[minute_sessions](minute_sessions-frozen-data.zip)。包 hash 与证据对应；仅保存实际响应及必要身份，无数据库/凭证。记录对比中出现的早期宽松模式异常未据此宣称根因已完全隔离，最终采用公开 strict_data 参数、记录错误记忆及 Windows 原子写入重试后全部通过；旧宽松实验包不能用于正式回放。

分钟验证包含预热、午休、两日 480 次原生 every_minute 回调，以及每天收盘显式核对 240 次回调；原生调度时间与 QMT 分钟索引不同，详见运行说明。股票/ETF 竞价、成交量及指数精度差异沿用 G0 数据证据，不进行统一倍数处理。

## 任务及网页

[真实进程验收](recovery-suite.json)：排队/运行中取消、已验证的子进程树终止、被原生引擎吞掉的回调异常映射 FAILED、8秒超时终止、API 非正常退出后核验遗留进程并终止/标记 INTERRUPTED，不重跑。独立验收端口7243，未操作共享 QMT 或真实资金。

[浏览器验收](browser-final.json)：离线回放按钮、原生报告、编辑并保存源码、语法失败显示、运行任务停止、归档恢复保留修订、实际初始权益说明；page_errors 为空。截图：offline-replay.png、native-report.png、failure.png、cancelled.png。测试脚本使用现有 Edge 无头浏览器，不操作 QMT GUI。测试中 Monaco 输入定位和 AntD 两字按钮空格匹配问题已修正；最终通过以此文件为准。

原生报告初始资金标签实际使用首日收盘权益；网页补充引擎实际初始权益说明，原 HTML/CSV/metrics 未改写。测试验证原产物保留。

## 最终检查及边界

[最终检查](validation.json)：18 项针对性测试通过，覆盖 SQLite 升级/不变性、恢复 PID 身份与早期 runner 标记、产物校验、冻结缺键/损坏/写入错误、预览窗口、交易拒绝零 Gateway 调用、报告说明；生产构建、pip check 和 diff 检查通过。TestClient 弃用警告和 Vite 大包体提示保留为已知问题。

数据服务 features=[data]，后端 big_qmt ready；应用 trading=false。底层既有 Gateway 9000 仍启用交易，不宣称它全局只读。真实验收没有发送下单、撤单或资金操作。

回放只承诺已验收有限确定性策略及相同软件/配置身份，升级需重新记录；不承诺任意 Python、随机数、当前时钟、外部模块/文件可冻结。历史 ST/新股规则、精确涨跌停、财务历史可得时点、历史成分/行业未通过；Tick/期货期权不纳入首版。总体数据覆盖仍是有限窗口。用户可信策略的独立进程不是恶意代码沙箱。

[运行说明](../../QUANTRADAR2_RUNBOOK.md) · [开发计划](../../QUANTRADAR2_DEVELOPMENT_PLAN.md) · [当前状态](../../CURRENT_STATE.md)
