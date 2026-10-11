# 强制缓存回测

2026-10-11。用户要求所有策略必须先缓存再计算。

新建任务 API 默认 prepared，兼容旧客户端提交的 auto/live/record 名称但强制转换 prepared。缺少有效证券池/历史窗口、基准无效或分钟频率均在排队前拒绝。执行器仅允许 prepared 和本地 replay，无法通过直接任务请求启动在线模式。已有运行进程不受源码更新影响；历史记录和回放不变。

网页仅保留强制缓存设置，恢复旧任务也采用 prepared。数据准备失败、校验失败及查询超出缓存边界不会退回网络。当前支持固定池日频；动态池必须提供覆盖完整查询范围的数据清单（现有最多100证券），分钟预准备尚不支持，因此阻止启动，不宣称所有策略类型已支持。

45 项 tests/v2、TypeScript 类型检查、生产构建通过。浏览器检查设置及请求 data_mode=prepared，写请求拦截，不新建回测、不修改策略；见 browser.json 和 settings.png。既有 prepared 测试涵盖缓存复用零连接、损坏和越界拒绝。

当前 e98119ae 仍运行旧 record 进程；scripts/v2_restart_when_idle.py 等队列清空后加载新版，var/quantradar2/mandatory-deployment.json 记录加载结果。加载前更新页面提交 prepared 已受旧 API 的严格校验；后端旧客户端强制转换须待进程重启生效。
