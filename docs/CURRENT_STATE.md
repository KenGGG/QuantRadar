# QuantRadar2 Current State

2026-10-11 强制缓存改造：源码和构建已取消新任务在线回退，旧模式名统一转换 prepared；缺数据清单和分钟频率拒绝启动，runner仅允许prepared/replay。45项后端测试、类型检查、构建和浏览器提交检查通过。当前运行任务保留旧路径；后端完整策略待队列清空后重启加载，加载标记见var/quantradar2/mandatory-deployment.json。网页已只提交prepared。

Updated: 2026-10-11 (Asia/Shanghai). [目标状态](ACTIVE_PHASE.md) · [开发计划](QUANTRADAR2_DEVELOPMENT_PLAN.md) · [运行说明](QUANTRADAR2_RUNBOOK.md)

- 网页/新建策略默认自动数据模式：有明确DATA_REQUIREMENTS或请求计划的日频任务先预准备；无声明或分钟任务查询QMT并记录供回放。错误声明和显式prepared仍严格报错，中文提示说明证券池及预热要求。保存实际模式/解析原因，API省略模式仍live以兼容旧调用。45项测试、构建及网页默认/请求检查通过，API已加载新版；没有新增真实回测。见[自动模式验收](acceptance/quantradar2-auto-mode/README.md)。

- 策略编辑及预览的日期控件支持中文日历、直接输入和底部年份/月跳转。2019-01-01手输/点击、原年月标题及闰日选择验证通过，运行请求日期与界面一致；类型/构建通过。验收模拟保存与提交，不新增任务或修改策略。见[历史日期验收](acceptance/quantradar2-dates/README.md)。

- 默认首页为聚宽式策略列表，顶部入口及“新建空白策略”按钮可见。支持搜索/分页/打开编辑、跨全部修订历史回测计数与筛选、复制、归档与恢复。命名创建后进入真正空编辑器；空源码可保存，前端/API拒绝空代码运行，新建清空旧摘要/日志。44项测试、生产构建及真实创建/编辑保存/搜索/历史/手机浏览器验收通过，API已加载新版。测试草稿已归档，旧策略与回测产物保留。见[策略列表验收](acceptance/quantradar2-strategy-list/README.md)。

- 用户已授权补齐应用统计：Alpha/Beta、相对超额收益、信息比率、策略/基准波动率、日均超额、超额回撤/Sharpe、收益/Sharpe/Sortino、净卖出成交胜率等及全部侧栏1/3/6/12月滚动表。统一250日、4%无风险和样本标准差，缺数据/零分母显示“—”，原生报告与产物仍保留。策略编辑页为深色代码/右侧六项摘要与图/底部日志，高级设置弹窗、查找/换行/快捷键/日志收起可用。43项测试、公式边界、CSV、类型/构建和真实回测桌面/手机浏览器检查通过。见[指标与编辑器验收](acceptance/quantradar2-metrics-editor/README.md)。


- QMT本地预准备已上线，固定证券池日频支持预准备模式；缓存命中无需连接QMT，执行前关闭QMT连接，任务固定独立SHA256数据快照。首次完整1681日任务183c460311b14371a09cbec982ba29aa约137.56秒，缓存复用80cb8c0f9aa94ae0afe9661b7246f2f4约38.79秒，离线回放b2cb643d329f47819e79d1f1d6838850约38.38秒，均SUCCEEDED。三份运行的8份CSV逐字节一致，金融指标一致。旧5053fab2已有1147日权益和1051日因子/选择一致。原修订ec1321ab5cfd4cbbb38aeecc4065ea8e、参数和参考日不变，2019-01-02至2025-12-05完整覆盖，96日现金warmup及原生报告有效。43项tests/v2、前端生产构建和pip check通过；API/回测日志目录独立。见[预准备验收](acceptance/quantradar2-data-preparation/README.md)。分钟/动态池等仍使用旧模式，历史数据资格限制不变，G3未启动。

- 应用Provider的双日期/count=None日历查询显式使用自然日数上界，不再默认截断250。旧926664c872a14a42a532629700e17468仍为超时失败，旧5053fab22fc24ea29fe970888bd5f785在API恢复时标记INTERRUPTED；其原产物完整保留，不把这些旧任务改为成功。此前日历修正证据保留于[日历修正](acceptance/quantradar2-calendar-correction/README.md)。

- 首版 G0/G1/G2 已验收，G3 未启动。实际仓库 D:/Projects/QuantDev/QuantRadar2；本地分支 codex/quantradar2-workbench；未推送或合并。
- 外部 BulletTrade 为 D:/Projects/BulletTrade，0.10.0，提交 9c34c213753c51883852a7bf528dd216b2c8fa3f；G0 审查时与上游一致。原引擎及配置未修改，外部工作树干净。旧 vendor 0.9.2 不作为 V2 引擎。
- Windows Python 3.12.15、Node 24.21.0、npm.cmd 11.19.0、Git 2.56.0.windows.2；独立 .venv-v2，依赖声明 pyproject.toml、环境快照 requirements.lock。npm.ps1 受执行策略限制，使用 npm.cmd。
- V2 API/WebUI 在 http://127.0.0.1:7242/；独立数据服务 127.0.0.1:58621，features=[data]、big_qmt ready。API trading=false；底层既有 Gateway 9000 仍启用交易能力。没有调用真实交易接口。
- SQLite 仅存策略、不可变修订、任务及产物索引，默认 var/quantradar2/metadata.sqlite3；schema2 可保留已有数据升级。策略可复制、归档、恢复；运行产物独立保存，未接入旧数据库或 DataHub。
- 单任务 FIFO 子进程、增量日志、停止、超时和身份核验恢复可用。重启核验并终止本应用遗留运行器，完成标记有效则恢复结果，否则 INTERRUPTED，不重跑原任务；排队任务继续排队执行。
- 网页提供策略工作台、记录/原生报告、数据连接及有限预览。源码和参数可恢复为新任务；没有实盘交易 UI、任意 RPC 或其他数据源。
- 冻结记录保存实际 Provider 响应及请求键/hash、来源、策略/参考日期/引擎/配置/依赖/适配代码身份。回放不连接 QMT、不读取线上凭证、缺请求或身份不符失败；支持有限、确定性策略，不是任意 Python 的通用可复现环境。
- 四组策略（股票买入持有、ETF 日频双均线、固定 ETF 池月度动量、分钟回调）均完成真实行情记录/API 离线回放/直接运行器离线回放；三份原生 CSV 和核心指标逐项精确一致。冻结包和证据见 G2 验收目录。
- 最终 18 项测试通过；真实取消/超时/回调错误/非正常重启及浏览器验收通过。V2 生产构建、pip check 通过；TestClient 有依赖弃用警告，前端有大包体警告。
- 股票/ETF/指数日线和分钟仅证明已归档有限窗口；研究 RPC 21 接口测试包含空值、无效乘数、pandas.Panel 不兼容、历史成分时点未通过等限制，未冒充完整回测能力。
- BigQMT 历史涨跌停字段缺失，当前原生 current-data 请求由 BulletTrade 自身估算；历史 ST/新股规则、财务历史可得时点、历史成分/行业资格未通过。Tick/期货期权不纳入首版资格。
- 原生 HTML 与原生指标产物不覆盖。用户授权的新详情页使用单独应用统计，不写回原生报告。原报告把首日收盘权益标为初始资金，网页补充引擎实际初始权益说明；分钟调度/竞价/单位差异见 G2 及运行说明。
- 可信 Python 策略的独立进程不是恶意代码沙箱。V1源码和旧文档均已按用户要求删除，历史版本可在Git追溯；运行数据库、凭证、环境和生成目录不提交。

- 后续页面修正已恢复原版深蓝导航、工作区标签、双栏深色编辑器/右侧结果；生产构建及桌面/手机浏览器检查通过。全项目扫描后清理370个开发临时文件（约22.7 MiB），主SQLite与33条任务及其产物目录完整。详见 [页面恢复与清理](acceptance/quantradar2-ui-cleanup/README.md)。

- docs 已按用户要求删除193个旧 QuantRadar 开发文档文件（30159799字节）；仅保留本次四份主文档和四个验收目录。主SQLite和运行产物未改动。

- 项目已彻底移除V1功能代码/目录、旧入口、vendor及旧依赖清单；frontend dev/build统一V2。当前服务依赖日志集中于var/quantradar2/logs。清理后18项测试、标准生产构建、pip check通过；详见代码清理记录。
