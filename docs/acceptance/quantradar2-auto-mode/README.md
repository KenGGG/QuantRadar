# 新策略数据模式兼容

2026-10-11。新策略此前默认prepared，未声明 DATA_REQUIREMENTS 时在入队前失败。

网页默认及新建策略使用auto。API保存实际解析后的data_mode：日频且源码声明 DATA_REQUIREMENTS 或请求提供 data_requirements 时严格验证后选择prepared；否则选择record，按需查询QMT并记录供回放。分钟auto也使用record。记录requested_data_mode及中文data_mode_reason，不把按需查询描述为全量预下载。没有猜测证券池、执行源码推断依赖或删除预准备加速。

显式prepared仍要求完整证券池及历史窗口；缺失/错误声明给出中文修正提示，不自动掩盖不完整数据需求。warmup_bars有效范围60至5000，84只是示例。原API省略data_mode仍保持live以兼容旧调用。没有改变旧任务请求、prepared适配/指纹、引擎或QMT。

45项测试、生产构建、[网页验收](browser.json)通过。API测试覆盖无声明auto、源码/显式计划prepared、分钟record、错误计划不回退、显式prepared中文提示及语法错误；均使用独立临时数据库且不运行任务。网页验收[设置截图](settings.png)确认默认auto及提交参数；模拟保存/入队，不修改用户数据。

确认没有运行/排队任务后重新加载API，新版接口与页面已在7242提供。用户刷新后即可重新发起策略回测；动态策略record模式仍按需访问数据，不保证预准备的离线加速。
