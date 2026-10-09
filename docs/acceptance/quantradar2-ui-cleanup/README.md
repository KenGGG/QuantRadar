# 聚宽风格恢复与项目清理

日期：2026-10-09（Asia/Shanghai）。结论：页面风格恢复并通过检查，之后完成整个项目目录扫描及开发临时文件清理。

## 页面恢复

对照 frontend/src/App.tsx、index.css 和原 StrategyWorkbench，恢复深蓝顶部导航（#22315c）、白色工作区标签、原 logo 条形标志、46%/54% 左右双栏、深色 Monaco 编辑器、右侧回测参数/结果/浅色日志，以及原按钮配色和小圆角。保留 V2 的三个入口，报告在右栏预览，也可独立打开原生报告。

复用的是原版视觉结构及样式参数，没有重新接入旧 DataHub/API。日频、分钟、任务操作、冻结回放和 SQLite 数据协议未改。窄屏自动改为上下布局。

npm.cmd run build:v2 --prefix frontend（含 tsc）通过；既有大包体提示保留。无头 Edge 检查顶部颜色、桌面左右布局、Monaco、记录导航、恢复源码/参数为草稿、原生报告 iframe、数据页及390px手机无整页水平溢出；无 pageerror。证据见 [browser.json](browser.json)。本次浏览器检查使用已有记录，没有新增运行或改写历史策略。

截图：[桌面工作台](workbench-desktop.png)、[带报告的工作台](workbench-report.png)、[手机布局](workbench-mobile.png)。

## 全目录扫描与清理

扫描范围为 D:/Projects/QuantDev/QuantRadar2，包含隐藏目录、Git、依赖、运行产物和旧版源码；不遍历链接目录，不触碰外部 BulletTrade 或 QMT。扫描前55224个文件，约1097.8 MiB，无无法读取项。主要体积是 .venv-v2（约594.6 MiB）、frontend/node_modules（约276.9 MiB）、var/quantradar2（约105.0 MiB）；不能将安装依赖当成垃圾删包。

清理21个明确目标，共370个文件、23788565字节（约22.7 MiB）：

- 本项目 pytest/Python 可再生缓存3处。
- 10个已结束的 G1/G2 开发烟测或早期直接回放目录：不在主SQLite任务记录中，也不被正式验收文档引用。
- 2个独立恢复测试运行目录，确认无存活应用进程使用。
- 旧烟测 JSON/日志和前一次API日志5个。
- G2早期归档诊断截图1张；正式归档恢复的通过记录保留。

删除前逐项校验绝对路径在项目内，无重解析点，不属于已注册任务，无相关活进程；全部目标清理后再确认不存在。详见 [清理清单](cleanup.json)、[扫描前](inventory-before.json)、[扫描后](inventory-after.json)。

## 保留项及理由

- 主SQLite、33条已注册任务及其目录、当前配置/token/PID/服务日志：在用状态和历史记录。
- 正式验收引用的直接回放目录、G0/G1/G2证据和四个冻结包：用于复核，不是临时垃圾。
- requirements-v2-dev.txt 与三个 v2_*acceptance.py：可重复验收工具，不是一次性脚本。
- .venv-v2、node_modules、当前 dist-v2：当前运行/构建所需。
- frontend/src 原版入口及 tracked dist、backend/quantradar、旧脚本/测试/文档、vendor/bullet-trade：V1保留和历史基线，V2不加载它们。没有以“未被V2使用”为由删除旧系统或旧证据。
- .git：提交历史。

全目录未发现非依赖目录中的 .tmp/.bak/.orig/.rej 或 tmp_/temp_ 文件候选。旧版 DataHub/Kronos 等源码仍保留，但不属于本次新产生的开发垃圾；若未来决定完全放弃V1，应另做整体归档/移除，不能把零散删除当作依赖迁移完成。

清理后API健康正常、trading=false、worker_error=null；33条任务及运行目录完整。未修改 BulletTrade 引擎、QMT、数据源或任何真实交易接口。

## 后续 docs 专项清理

用户明确要求仅保留本次文档后，删除193个旧 QuantRadar 开发文档文件，共30159799字节（约28.8 MiB），包含旧00–07规范、DataHub/Kronos计划、superpowers、legacy及旧验收目录。现仅保留 docs 根目录四份本次主文档，以及 acceptance 下 quantradar2-g0/g1/g2/ui-cleanup 四个目录。本节取代上文对旧文档的保留决定；扫描前后JSON仍作为此前清理的历史快照，不代表本次删除后的文件列表。旧版源码、主SQLite、任务及原生报告均未改动。
