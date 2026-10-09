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
