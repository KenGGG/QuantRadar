# QuantRadar

QuantRadar 是面向本地单用户的 A 股量化研究平台，基于 BulletTrade 回测引擎，提供策略编辑、日线回测、报告回放、数据治理，以及 Alpha101、ETF、Qlib 和 Kronos 研究入口。

数据遵循 **外部采集 → 本地版本化 → 审计发布 → Provider → 回测**。回测固定读取本地数据版本，禁止在执行过程中临时联网补数。

当前进度以 [ACTIVE_PHASE](docs/ACTIVE_PHASE.md) 为准；以下说明依据截至 **2026-09-14** 的代码和验收记录。Alpha101 / ETF 数据补充 V2 的 G0–G4 已记录完成，但这不代表全部市场数据完整，也不代表严格复现 WorldQuant 101 已通过。

## 当前能力

| 模块 | 已实现范围 | 当前边界 |
| --- | --- | --- |
| 本地回测工作台 | 策略保存与重开、日线回测、历史配置与源码回放、指标及 CSV / HTML 报告 | 已验收买入持有、双均线和周频多股票场景；不承诺完整 JoinQuant 兼容 |
| DataHub | 基础与补充 Dolt 配对发布、候选分支、审计门禁、采集日志、统一日更协调、覆盖率与失败分组 | 下载成功与正式发布分开；覆盖范围按数据集、字段、日期及 release 判断 |
| Alpha101 | 101 条公式依赖目录、原始量价输入、行业及总市值接入 | 原始工程模式的输入资格为 82 READY / 19 PARTIAL，不能据此宣称 101 条公式均完成独立验证 |
| ETF 研究 | 固定 10 只 ETF 原始日线、证券身份、既有 BulletTrade 成交回放 | `ETF_RAW` 可作研究；ETF 复权研究序列与严格公司行为账户尚未合格 |
| 行业与市值 | 归档申万资料重解析、三级代码分组、已有东财载荷总市值提取 | 历史可得时间不完整；行业名称、分类版本与 WorldQuant 行业口径等价性未验证 |
| Qlib | 数据构建、参数选择、walk-forward 样本外研究及报告链路 | 依赖本地真实数据与对应运行环境 |
| Kronos | 数据审计、独立 GPU 运行时、研究流水线 | 研究用途；不构成实盘准入，历史指数池与状态覆盖仍有限制 |
| 研报工作流 | 企业预警通 → MinerU → Agnes → 证据与日报，配套查看页面和飞书 outbox | 需独立服务与凭据；NotebookLM 路线暂停，连续七日运行未完成验收 |

本地工作台验收见 [日线回测记录](docs/acceptance/local-backtest/README.md)，DataHub 阶段记录见 [DataHub V2](docs/acceptance/datahub-v2/active-phase-completed.md)。历史验收结果只适用于记录中的版本和场景。

## Alpha101 与 ETF：数据究竟齐不齐

**基础 Dolt 已有原始价格和复权资料，应优先复用。** `FINAL_ADJ` 与 `BAO_ADJ` 是不同来源的价格模式，不能直接互相填补缺口。已有复权资料不等于已经发布跨来源统一调整序列，也不等于真实分红、送配及账户权益处理已完整。

最新阶段验收引用的固定研究版本如下；这是可复核的验收基线，不是自动跟随更新的“最新数据”指针。

| 标识 | 固定值 |
| --- | --- |
| release_id | `R9c1b6c13965dc457` |
| 基础 Dolt commit | `uhdpedb4pr97ve80aq6nrabr66atsqtq` |
| 补充 Dolt commit | `r4t6rm3fdtb06rqpk0bmbtp2hn638a5r` |

该版本的 Alpha101 输入资格记录为：

| 模式 | READY | PARTIAL | BLOCKED | 含义 |
| --- | ---: | ---: | ---: | --- |
| `ALPHA101_RAW_ENGINEERING` | 82 | 19 | 0 | 82 条量价依赖；18 条行业中性化与 #56 总市值依赖仍为 PARTIAL |
| `ALPHA101_ADJ_RESEARCH` | 0 | 0 | 101 | 尚未发布跨来源审计的统一调整序列，不表示基础库没有复权数据 |
| `ALPHA101_PIT_STRICT` | 0 | 0 | 101 | 历史股票池、行业公开时间及相关时点资格未完整合格 |

上述数量是**输入能力分组**，不是逐公式正确性、收益表现或严格 WorldQuant 复刻的验收数量。原始工程模式不要求先补齐所有公司行为公告，但不能将结果解释为复权或总回报结果。

行业资料已有 12,536 条规范化区间、553 个三级代码，并提供一级、二级、三级代码输入；归档文件缺少可验证的历史公开时间，因此不能宣称行业 PIT 齐全。总市值来自已有历史载荷，不应当作流通市值，历史时点可得性仍为 PARTIAL。

ETF 研究池为 `510050.SH`、`510300.SH`、`510500.SH`、`159919.SZ`、`159915.SZ`、`159901.SZ`、`159902.SZ`、`159903.SZ`、`510180.SH`、`510880.SH`。2020-01-01 至 2026-08-31 的检查区间内，159901 缺 2021-03-10、159915 缺 2021-02-08；缺日保留为未知，不能直接认定停牌。公司行为目前只有 7 只 ETF 的 8 条事件样本，交易规则也仅部分覆盖，严格账户回放仍不具备完整条件。

详细依据：[价格模式规则](docs/acceptance/alpha101-etf/alpha101_price_mode_rules.md)、[行业发布记录](docs/acceptance/alpha101-etf/g3_sw_industry_hierarchy_release.md)、[模式资格](docs/acceptance/alpha101-etf/g3_alpha101_mode_qualification.md)、[ETF 原始价回放](docs/acceptance/alpha101-etf/g2_etf_provider_raw_replay.md)、[阶段验收](docs/acceptance/alpha101-etf/g4_final_acceptance.md)。

## 数据架构与约束

```text
已有基础 Dolt（只读） ─────────────────────┐
                                         ↓
外部来源 → 原始资料留存 → 补充 Dolt 候选 → 审计 → 配对 release
                                                  ↓
                                           固定版本 Provider
                                                  ↓
                                      BulletTrade / 研究任务
                                                  ↓
                                         快照、报告、WebUI
```

- 基础库默认位于 `/data/investment_data`，SQL 端口 `3307`；补充库默认位于 `/data/quantradar_data`，端口 `3308`。新增事实在补充库治理，Provider 不写基础库。
- 同一次运行固定 `release_id`、`base_commit`、`supplemental_commit` 与单位版本。新版本日线单位为股、元；旧版本保留其原有单位解释。
- 优先复用已有 Dolt 和归档原始资料；外部接口只用于采集阶段，不能成为回测缺失数据的在线回退。
- 行情、上市退市、代码变更、指数历史成分、停牌 / ST / 涨跌停、公司行为、财务可得时间分别审计。不能用今天的指数成分回填历史，也不能将行情更新日期当作全部字段的更新日期。
- 估值基线仍保留 196 个失败项和 123 个历史未验证项，不能把成功子集称为全市场完整覆盖。严格 PIT 财务数据尚未齐备。
- Git 保存源码、契约和验收证据；Dolt 数据库、原始下载、模型、凭据及本地运行产物独立存放。

## 本地运行

需要 Python **3.11 或 3.12**、Node.js / npm，以及所用功能对应的本地数据库。BulletTrade 使用仓库内 `vendor/bullet-trade` 的 editable 安装。

```bash
make setup
cp .env.example .env
# 编辑 .env，配置本地连接后启动
./quantradar.sh start
```

访问 **http://127.0.0.1:7231**。FastAPI 托管构建后的 React 前端，异步回测 Worker 运行在应用进程内。Dolt、PostgreSQL 及独立研究服务需要另外准备，启动脚本不负责安装或启动这些依赖。

| 配置 | 用途 |
| --- | --- |
| `INVESTMENT_DATA_*` | 基础行情 Provider 只读连接，示例见 [.env.example](.env.example) |
| `DATAHUB_BASE_HOST` / `DATAHUB_BASE_PORT` | DataHub 基础库连接，默认 `127.0.0.1:3307` |
| `DATAHUB_SUPPLEMENTAL_HOST` / `DATAHUB_SUPPLEMENTAL_PORT` | 补充库连接，默认 `127.0.0.1:3308` |
| `DATAHUB_USER` / `DATAHUB_PASSWORD` | DataHub 数据库凭据 |
| `DATAHUB_SUPPLEMENTAL_REPO` / `DATAHUB_RELEASE_ROOT` | 补充库与配对发布目录 |
| `QUANT_RADAR_PG_URL` | 异步回测 PostgreSQL 连接；未配置时相关接口返回 503 |
| `QUANTRADAR_HOST` / `QUANTRADAR_PORT` | Web 监听地址，默认 `127.0.0.1:7231` |

DataHub 完整默认值见 [config.py](backend/quantradar/config.py)。基础库与 DataHub 的连接配置应保持一致；`.env.example` 尚未列出全部 DataHub 参数。启动预检仅检查默认 `3307` 端口，可达不代表补充库、发布清单及所有研究依赖就绪。

```bash
./quantradar.sh status
./quantradar.sh restart
./quantradar.sh stop
```

应用日志位于 `logs/quantradar.log`。此应用允许执行用户策略代码，面向本地可信单用户使用；对外提供服务前需要鉴权和执行隔离。部分详细交互报告使用 CDN，不能据此承诺报告在断网浏览器中完整渲染。

## 开发与验证

```bash
make test       # tests/unit 单元测试
make smoke      # 核心链路冒烟，需对应本地数据与服务
make dev        # FastAPI 开发服务
make research   # Qlib 参数选择与 walk-forward OOS 研究
make help       # 更多研报、Kronos 等命令
```

涉及 PostgreSQL 的测试需使用独立测试库并遵守仓库测试库保护规则。研报采集、模型安装和研究任务可能访问外部服务；`make research-deliver` 会发送日报，配置与运行前应明确其外部服务及发送目标。

本次 README 更新不替代运行环境验收。具体测试结果应查阅对应版本的验收记录。

## 代码与文档导航

| 路径 | 内容 |
| --- | --- |
| [backend/quantradar](backend/quantradar) | API、Provider、DataHub、回测与研究业务 |
| [frontend](frontend) | React / TypeScript 工作台 |
| [vendor/bullet-trade](vendor/bullet-trade) | 回测引擎源码基线 |
| [scripts](scripts) | 冒烟、采集、研究及运行辅助脚本 |
| [tests](tests) | 单元与集成验证 |
| [docs/ACTIVE_PHASE.md](docs/ACTIVE_PHASE.md) | 当前目标与阶段状态，唯一目标来源 |
| [docs/CURRENT_STATE.md](docs/CURRENT_STATE.md) | 已记录系统事实；具体版本范围以对应验收证据为准 |
| [docs/acceptance](docs/acceptance) | 分阶段验收记录与数据限制 |

分钟线、实盘交易、完整证券生命周期、完整历史指数成分 PIT、严格财务 PIT，以及完整 ETF 公司行为账户，均不在当前完整交付承诺内。
