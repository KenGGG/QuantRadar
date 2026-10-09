# QuantRadar2 G0 验收记录

日期：2026-10-09。当前状态：PASSED_WITH_RECORDED_DATA_LIMITATIONS。独立环境安装、pip check及离线隔离测试通过；真实数据专用链路可读21行日线。进入G1。

## 环境与版本

- 仓库基线 c950d67337de3b096bb03766beb9526714386f93；当前开发分支 codex/quantradar2-workbench，未推送。
- 本机BulletTrade提交 9c34c213753c51883852a7bf528dd216b2c8fa3f；git ls-remote确认本次检查时上游main与之相同，工作树干净。不是仅比较0.10.0版本字符串。
- 旧vendor标记0.9.2。engine、analysis、reporting、remote provider、big_qmt适配器、CLI、Gateway样例的文件身份已对比，见source-audit.json。
- 旧create_backtest支持use_real_price参数，新版已移除该关键字；V2只使用新版公开入口，不搬运旧关键字或修改引擎。
- 外部Python3.12.15加载D:/Projects/BulletTrade源码；V2另建.venv-v2，不更改旧环境。
- Node24.21.0、Git2.56.0.windows.2、npm.cmd11.19.0；npm.cmd ci及npm.cmd run build通过。构建有旧主bundle较大的提示，不是构建失败。

## 真实依赖审查

| 子系统 | 旧实现依赖 | V2处理 |
|---|---|---|
| FastAPI启动 | bootstrap_investment_data、worker、旧storage/DataHub | 独立quantradar2.api.app入口 |
| 回测运行 | InvestmentDataProvider、activate_backtest_release、base_lease、全局_FQ_LOCK | 独立回测子进程、数据专用provider |
| 任务 | 线程池及旧数据库，重启自动重试 | SQLite单队列、进程身份核验、禁止自动重跑中断任务 |
| 工作台 | release选择、实验保存、旧API | 复用编辑器/布局，迁移V2专用API及参数 |
| 报告 | BulletTrade原生generate_report/generate_cli_report | 保留原生结果，限定已登记产物路径 |

V1目录和历史数据均保留，不启动旧采集器、不删除旧数据库。

## 数据与应用层只读边界

- 原21接口及后续对比完整归档：qmt-research-21-20261009.json。已有六组行情样本通过不代表全市场覆盖。
- 创建独立127.0.0.1:58621数据服务，独立令牌和配置位于var/quantradar2（忽略提交）；明确--enable-data --disable-broker，未改旧服务或QMT策略。
- 离线tests/v2/test_data_only_boundary.py直接执行通过：place/cancel/account/orders/resolve请求均拒绝，Gateway get/post替身调用为0，features仅data。
- 真实调用仅admin.health，features=data、big_qmt ready、所有broker action unavailable，证据data-only-health.json；未向真实服务发送broker测试请求。
- Gateway内部交易/撤单开关仍true，如实记录。V2隔离适用于可信本地研究，不构成恶意代码沙箱，也不宣称Gateway自身只读。

## 已知非核心限制

证券全列表协议/分类未通过，历史成分、财务PIT未验收，旧财务Panel失败，因子全NaN、Tick/退市合约空、合约乘数异常。首版不依赖这些能力；研究RPC不自动补量价缺口。

## G1文件级实施清单

1. backend/quantradar2：SQLite元数据、任务监督、原生运行器、精简API和数据资格；不导入quantradar旧业务包。
2. frontend：新增V2入口、V2API和三页面，复用已有编辑/报告布局；保留V1入口及构建。
3. scripts：Windows独立启动/停止、连接检查、基线回测验收；仅终止本应用拥有且身份匹配的进程。
4. tests/v2：元数据不可变、任务恢复与隔离、真实回测/冻结回放差分验收。

后续仍按QUANTRADAR2_DEVELOPMENT_PLAN.md执行，非核心接口不纳入G0修复任务。

## 最终检查

独立环境pytest：1 passed；pip check：No broken requirements found；依赖锁requirements-v2.lock已固定。真实58621行情证据见data-only-price.json。G0通过的是本计划约定的可信研究应用层隔离，Gateway本身交易开关仍开启。
