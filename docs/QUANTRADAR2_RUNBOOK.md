# QuantRadar2 Windows 运行说明

当前只提供本机可信策略研究与模拟回测。现有大 QMT Gateway 仍可能开放交易，V2 专用数据服务禁用 broker；不要把其他服务地址当作 V2 数据服务。

## 启动

在 PowerShell 进入 `D:\Projects\QuantDev\QuantRadar2`，先启动并登录 QMT；涉及 QMT GUI 的操作手动完成。已有服务在运行时不要重复启动。

```powershell
& 'D:\Projects\BulletTrade\.venv\Scripts\python.exe' -B scripts/v2_data_service.py
```

另开终端启动 V2 API：

```powershell
& '.\.venv-v2\Scripts\python.exe' -B scripts/v2_api.py
```

访问 http://127.0.0.1:7242/ 。服务只绑定环回地址；端口占用直接报错，不关闭其他进程。应用元数据为 `var/quantradar2/metadata.sqlite3`，独立回测产物在 `var/quantradar2/runs/<任务ID>`。不启动旧版数据库或 DataHub。

数据服务配置和 token 在 `var/quantradar2`，不提交或复制到报告；不要公开整个运行目录。

## 停止和恢复

网页停止按钮仅停止本应用验证身份后的模拟任务；排队任务直接取消。前台 API 用 Ctrl+C 正常关闭。隐藏启动的 API 可使用：

```powershell
& '.\.venv-v2\Scripts\python.exe' -B scripts/v2_stop.py
```

该命令验证 API PID、创建时间和命令再停止。启动后，遗留任务先核验身份；已有有效完成文件的恢复结果，其他运行中任务标记 INTERRUPTED，不自动重跑。QMT 与数据服务不会随 API 停止。数据服务用其启动终端 Ctrl+C 关闭。

任务代码可信，进程分离不是恶意 Python 的沙箱。禁止在策略中调用外部交易客户端。

## 开发和依赖

独立 `.venv-v2` 使用 Python 3.12，安装 `requirements-v2.txt` 和 `-e D:\Projects\BulletTrade`。`requirements-v2.lock` 保存本机完整依赖快照，其中本地 editable 路径需要对应调整。网页测试可额外安装 `requirements-v2-dev.txt`，使用已有 Edge，不下载浏览器。

```powershell
npm.cmd ci --prefix frontend --ignore-scripts --no-audit --no-fund
npm.cmd run build:v2 --prefix frontend
$env:PYTHONPATH='backend'
& '.\.venv-v2\Scripts\python.exe' -B -m pytest tests/v2 -q
```

前端开发用 `npm.cmd run dev:v2 --prefix frontend`，访问 `http://127.0.0.1:5174/v2.html`。使用 npm.cmd，不修改系统执行策略。旧版页面入口和配置保留。

## 数据限制

历史涨跌停字段不可获取，当前仅对原生 current-data 请求省略这两个字段，让 BulletTrade 使用自身估算。真实历史 ST、上市初期规则与精确涨跌停资格未通过；报告实际配置明确列出限制。股票/ETF日线成交量按 Provider 返回单位，不全局乘100；首分钟可能含竞价合并。历史成分、财务历史时点、Tick、期货期权暂不进入首版回测资格。

原生日历 PNG 是可选产物，缺少 snapshot_selenium 时保留日历 HTML。原生指标直接展示，网页不重新计算。回测收益不是实际交易结果。

## 冻结记录与离线回放

新任务默认“记录数据”；成功后可下载 frozen_data.zip，并在记录页面创建“离线回放”。回放沿用不可变源码、参数和复权参考日期，在本机软件身份一致时运行，不读取线上数据配置、不连接 QMT。缺请求键、响应损坏、策略/引擎/依赖/原生配置/适配器身份不一致直接失败，不自动回源。旧实验任务未记录 strict_data 策略的冻结包不提供回放入口。

记录的是该任务真正使用的有限 Provider 响应，不是全市场行情仓库。回放资格仅涵盖已验收确定性策略；策略自行读取文件、联网、使用随机数/当前时间或未冻结外部模块，不能据此保证一致。升级代码或依赖后应在新身份下重新记录、重新验收，不跳过 hash 检查。

[四组首版夹具及验收结果](acceptance/quantradar2-g2/README.md) 在仓库内；运行目录中的源码、参数、日志、原生报告及冻结包按单任务保留。源码修订不可变；归档策略可在策略管理中恢复，归档不删除历史回测。

## 原生时间及报告口径

BulletTrade 0.10.0 的 every_minute 回调为 09:30–11:29、13:00–14:59；QMT 分钟行情索引是 09:31–11:30、13:01–15:00。分钟示例另在 15:00 显式核对当日 240 次回调，两个交易日共 480 次 every_minute 回调。遵循原生时序，未修改引擎。股票/ETF 首分钟可能合并竞价，指数价格有精度差异，不跨接口强行合并或全局换算成交量。

原生 CLI 报告概览把首日收盘权益显示为“初始资金”；网页顶部显示 metrics 元数据中的引擎实际初始权益，并解释标签口径。原生 HTML 下载、CSV、指标均保留原内容，不由网页重新计算。缺 snapshot_selenium 时日历 PNG 不生成，日历 HTML 仍可用；首版无需安装该可选组件。

验证中的 TestClient 弃用警告与 Vite 大包体提示已记录，不影响本次通过结果。前端使用生产构建访问 7242；源码变更后需重新执行 build:v2。
