# QuantRadar Research MVP 开发计划（收敛版）

**建议仓库文件名**：`docs/RESEARCH_MVP_IMPLEMENTATION_PLAN.md`  
**目标仓库**：`KenGGG/QuantRadar`  
**计划版本**：v1.1  
**日期**：2026-08-25  
**阶段目标**：`QUANTRADAR_RESEARCH_MVP_PASS`

---

## 0. 计划结论

本次只实现一条生产链：

```text
企业预警通
→ 三栏目元数据采集
→ PostgreSQL 入库
→ Research WebUI 核对标题清单 / 处理状态
→ PDF 候选筛选
→ PDF 下载 + SHA256
→ 共享 MinerU API 转 Source Markdown
→ Agnes 2.5 分块全文分析
→ 每日研究简报
→ 飞书发送
```

本次开发的唯一产品目标：

> **每天无人值守地把企业预警通前一日“热门研报、策略研究、金融工程”中符合条件的 PDF 研报读完，并通过飞书发送一份基于全文内容生成的研究简报。**

不得在本阶段扩展为“完整 Research 平台”。

---

# 1. 已确认前提

Gate 0 已完成，以下事实直接作为开发契约，不再重复探索：

### 1.1 企业预警通

三个栏目已验证可采集：

- 热门研报
- 策略研究
- 金融工程

上游报告存在稳定的 32 位 `source_report_id`，正式版本以：

```text
(source="qyj", source_report_id)
```

作为外部唯一键。

日期使用：

```text
publishDate=[start_date,end_date]
```

分页使用：

```text
size + from
```

“热门研报”没有公开热度分数，正式系统只保存：

```text
platform_order
snapshot_at
```

不得把 `platform_order` 命名或解释为 `hot_score`。

### 1.2 内容类型

PDF 可以直接通过 HTTPS 下载。

非 PDF 内容在 MVP 中统一：

```text
content_type = non_pdf
processing_status = unsupported_content
```

只保存元数据，不解析 HTML、微信公众号或其他网页正文。

非 PDF 不得导致整日任务失败。

### 1.3 MinerU

不在 QuantRadar 内安装第二套 MinerU。

统一使用现有共享服务：

```text
QUANTRADAR_MINERU_API_URL=http://127.0.0.1:58000
```

MVP 固定：

```text
MinerU concurrency = 1
```

仅调用现有 MinerU API；QuantRadar 只实现客户端适配层。

### 1.4 Agnes

Agnes 2.5 已验证能够输出合法结构化 JSON。

正式版本必须支持：

```text
短报告 → 整篇分析
长报告 → 分块分析 → 报告级汇总
```

严禁因超出上下文限制直接截断报告尾部。

### 1.5 飞书

飞书测试已验证成功。

现有机器人要求消息包含既定关键词，正式版本必须配置化：

```text
QUANTRADAR_FEISHU_REQUIRED_KEYWORD
```

不得把关键词写死在业务代码。

---

# 2. Scope Lock：本次只做什么

## 2.1 必须实现

1. Headless 持久化浏览器会话；
2. 企业预警通三个栏目采集；
3. 日期、分页、外部 ID、平台顺序快照；
4. PostgreSQL Research 独立数据模型；
5. PDF 内容类型判断；
6. PDF 下载、SHA256、页数校验；
7. MinerU API 调用；
8. Source Markdown 本地保存；
9. Markdown 质量检查；
10. Agnes 2.5 两套分析 Schema；
11. 长报告动态分块；
12. 报告级合并；
13. 最小 Evidence 引用检查；
14. 每日市场风向摘要；
15. 热门研报精华；
16. 策略/金融工程精选；
17. 飞书日报；
18. Outbox 防重复；
19. 独立 CLI；
20. 独立 systemd 定时任务；
21. 最小 Research WebUI，用于核对三栏目标题清单和处理状态；
22. 30 份样本、3 个历史日期、连续 7 天真实验收。

## 2.2 明确不做

以下内容全部禁止进入本 MVP：

- HTML / 微信正文解析；
- 向量数据库；
- Embedding；
- 知识图谱；
- 分析师排行榜；
- 长期观点变化追踪；
- 自动生成 Hypothesis；
- 自动生成策略代码；
- 自动调用 BulletTrade 回测；
- 与 Kronos 联动；
- GitHub 私有研报知识库；
- PDF/Markdown 上传 GitHub；
- 市场情绪指数；
- “卖方研报因子”；
- 自动交易；
- 第二套 MinerU；
- 新的通用任务调度框架；
- Celery / Redis / Kafka；
- 为 Research 改造现有回测 Worker。

一旦实现过程中出现上述需求，一律记录到 `Future Work`，不得插入当前开发。

---

# 3. 与现有 QuantRadar 的边界

Research MVP 必须是 QuantRadar 的独立后端子模块，但不能侵入现有回测核心。

建议目录：

```text
backend/quantradar/research/
├── __init__.py
├── cli.py
├── config.py
├── models.py
├── storage.py
│
├── collector/
│   └── qyj.py
│
├── download/
│   └── pdf.py
│
├── parser/
│   ├── mineru.py
│   └── quality.py
│
├── llm/
│   ├── base.py
│   ├── agnes.py
│   ├── chunking.py
│   ├── schemas.py
│   └── prompts/
│       ├── market_report.md
│       └── quant_report.md
│
├── digest/
│   └── builder.py
│
├── notify/
│   └── feishu.py
│
└── pipeline.py
```

测试：

```text
tests/unit/research/
tests/integration/research/
```

本阶段：

- 不修改 BulletTrade；
- 不修改 Kronos runtime；
- 不修改 `BacktestWorker`；
- 不把 Research 夜间任务放进 FastAPI 主进程；
- **允许对 FastAPI 增加只读 Research 查询 API**；
- **允许对 React 前端增加一个最小“Research”栏目**，仅用于核对标题清单、栏目归属和流水线状态，不建设完整研究工作台。

---

# 4. Git 开发约束

从执行时最新 `main` 建独立分支和 worktree：

```bash
git checkout main
git pull --ff-only

git worktree add .worktrees/research-mvp -b feat/research-mvp main
```

记录实施起点：

```bash
git rev-parse HEAD
```

写入开发记录。

原则：

1. 只从最新 `main` 开发；
2. 不复用 Kronos 旧 worktree；
3. 每个 Task 独立 commit；
4. 每个 Task 必须“测试先行 → 最小实现 → 针对性测试 → commit”；
5. 不在同一个 Task 顺手重构无关代码；
6. 完成后统一 PR；
7. 未通过真实验收前不得声明 `QUANTRADAR_RESEARCH_MVP_PASS`。

---

# 5. 数据与文件契约

## 5.1 PostgreSQL

Research 使用独立模型，不把字段塞入现有 `BacktestRun` / `Experiment`。

最小只建 7 张表。

### `research_reports`

一篇研报本体。

核心字段：

```text
id
source
source_report_id
title
institution
authors
publish_date
category
industry
security
content_type
source_payload
created_at
updated_at
```

唯一约束：

```text
UNIQUE(source, source_report_id)
```

### `research_report_snapshots`

记录同一篇报告在哪个栏目、哪次采集中出现。

```text
id
report_id
target_date
channel
platform_order
snapshot_at
raw_payload_hash
```

唯一约束建议：

```text
UNIQUE(report_id, target_date, channel)
```

### `research_artifacts`

记录 PDF 与 Markdown。

```text
report_id
pdf_path
pdf_sha256
pdf_size
pdf_pages
platform_pages
page_count_match

markdown_path
markdown_sha256
parser
parser_version
parse_quality
```

### `research_stage_runs`

用于断点续跑。

```text
id
report_id
stage
status
attempt
input_hash
output_hash
started_at
finished_at
error_code
error_message
```

MVP 不实现分布式 Worker，因此暂不引入复杂 lease 调度。

状态固定：

```text
PENDING
RUNNING
SUCCESS
FAILED
UNSUPPORTED
```

stage 固定：

```text
DOWNLOAD
PARSE
ANALYZE
VALIDATE
```

### `research_analyses`

```text
report_id
analysis_type
model
prompt_version
input_hash
output_json
output_markdown
research_value
reproducibility
created_at
```

### `research_daily_digests`

```text
target_date
content_md
content_json
digest_hash
completeness
created_at
```

### `research_outbox`

```text
notification_key
target_date
digest_hash
status
attempt
payload_hash
sent_at
last_error
```

`notification_key` 必须唯一。

---

## 5.2 本地文件

统一根目录：

```text
QUANTRADAR_RESEARCH_DATA_DIR=/data/quantradar/research
```

结构固定：

```text
/data/quantradar/research/
├── raw/
│   ├── metadata/YYYY/MM/DD/
│   └── pdf/YYYY/MM/DD/
│
├── source_md/YYYY/MM/DD/
├── analysis/YYYY/MM/DD/
├── digest/YYYY/MM/
├── debug/<run_id>/
└── logs/
```

禁止将 PDF 和完整 Source Markdown 放入 Git 仓库。

---

# 6. 候选池规则：必须简单、确定、可解释

MVP 不做 AI 预筛选，不做 embedding，不做复杂推荐算法。

对前一日三个栏目的全部元数据完成采集后，全文分析候选按固定规则生成。

默认配置：

```yaml
research:
  candidate:
    hot_pdf_limit: 10
    strategy_pdf_limit: 20
    financial_engineering_pdf_limit: 10
    max_unique_reports_per_day: 30
```

规则：

1. 热门研报：按 `platform_order` 从前往后取前 10 篇有 PDF 的报告；
2. 策略研究：按 `platform_order` 从前往后取前 20 篇有 PDF 的报告；
3. 金融工程：按 `platform_order` 从前往后取前 10 篇有 PDF 的报告；
4. 按 `source_report_id` 去重；
5. 全日最多分析 30 篇唯一报告；
6. 同一报告出现在多个栏目，只下载、解析、分析一次；
7. 栏目关系仍完整保存在 snapshots 中。

以上参数可配置，但第一版不做自动调参。

---

# 7. Task 1：Research 基础骨架、配置和存储

## 目标

建立 Research 独立模块、配置、数据库和幂等基础，不接企业预警通。

## 文件

新建：

```text
backend/quantradar/research/__init__.py
backend/quantradar/research/config.py
backend/quantradar/research/models.py
backend/quantradar/research/storage.py
tests/unit/research/test_storage.py
tests/unit/research/test_config.py
```

修改：

```text
pyproject.toml
.env.example
```

只新增确实需要的依赖：

```text
playwright
```

优先复用现有：

```text
httpx
pydantic
sqlalchemy
```

不要加入 Celery、Redis、RQ 等。

## 测试先行

至少覆盖：

```python
def test_report_unique_by_source_and_source_report_id(): ...
def test_snapshot_keeps_same_report_in_multiple_channels(): ...
def test_stage_success_is_idempotent(): ...
def test_outbox_notification_key_is_unique(): ...
def test_config_requires_local_data_dir_and_profile_dir(): ...
```

## 验收

- Research 表可独立初始化；
- 不影响现有 QuantRadar 回测表；
- 现有核心测试不因 Research schema 变化而失败；
- `.env.example` 不出现真实 Cookie、API Key、Webhook。

## Commit

```text
feat(research): add MVP storage and config
```

---

# 8. Task 2：企业预警通 Collector

## 目标

把 Gate 0 脚本固化为正式 Collector。

## 文件

新建：

```text
backend/quantradar/research/collector/qyj.py
tests/unit/research/test_qyj_collector.py
tests/fixtures/research/qyj/
```

## 实现范围

只支持：

```text
HOT
STRATEGY
FINANCIAL_ENGINEERING
```

正式参数：

```text
publishDate
size
from
```

浏览器：

```text
Headless Chrome
Persistent Profile
```

必须使用独立 Profile：

```text
QUANTRADAR_QYJ_PROFILE_DIR
```

Collector 负责：

1. 启动持久化 Headless 浏览器；
2. 验证登录状态；
3. 获取 Gate 0 已确认的动态鉴权信息；
4. 逐栏目采集指定 `target_date`；
5. 完整分页；
6. 标准化报告；
7. 写 `research_reports`；
8. 写 `research_report_snapshots`；
9. 保存原始 JSON 快照。

## 登录状态

至少：

```text
AUTH_OK
LOGIN_REQUIRED
CAPTCHA_REQUIRED
AUTH_UNKNOWN
```

认证失败时：

- 停止采集；
- 保存 screenshot；
- 保存页面 HTML；
- 返回明确 error_code；
- 不自动绕过验证码。

## 测试

使用 Gate 0 脱敏 fixture，禁止单元测试依赖实时网站。

至少：

```python
def test_normalize_stable_source_report_id(): ...
def test_pagination_uses_size_and_from_without_duplicates(): ...
def test_same_report_across_channels_creates_one_report_and_two_snapshots(): ...
def test_platform_order_is_preserved(): ...
def test_auth_failure_stops_collection(): ...
```

## 真实验收

选择 Gate 0 已验证日期重新跑两次：

```text
栏目数量一致
source_report_id 集合一致
栏目内顺序一致
数据库无重复
```

## Commit

```text
feat(research): collect qyj report metadata
```

---

# 9. Task 3：PDF 下载与 Artifact Registry

## 目标

只处理 PDF；非 PDF 明确标记但不阻塞。

## 文件

新建：

```text
backend/quantradar/research/download/pdf.py
tests/unit/research/test_pdf_download.py
```

## 实现

候选池由确定性规则产生。

PDF 下载使用现有 `httpx`。

流程：

```text
report
→ attachment type
→ PDF ?
   ├─ no → UNSUPPORTED
   └─ yes
       → download
       → temp file
       → validate PDF
       → SHA256
       → page count
       → atomic rename
       → artifact record
```

要求：

- 先写 staging 文件；
- 下载完整后原子改名；
- 相同 SHA256 不重复写；
- 同报告已有成功 artifact 时直接 skip；
- PDF 页数以 `pdfinfo` 或等价 PDF 专用解析器为事实源；
- 平台页数只做交叉检查；
- `file` 命令不得作为页数事实源；
- 下载失败只影响单篇报告。

错误码至少：

```text
PDF_DOWNLOAD_FAILED
PDF_INVALID
PAGE_COUNT_MISMATCH
UNSUPPORTED_CONTENT
```

`PAGE_COUNT_MISMATCH` 默认只告警，不直接失败。

## 测试

```python
def test_download_writes_atomically_and_hashes_pdf(): ...
def test_existing_same_hash_is_not_downloaded_again(): ...
def test_non_pdf_is_unsupported_not_failed(): ...
def test_page_count_mismatch_is_recorded(): ...
```

## Commit

```text
feat(research): download and register PDF artifacts
```

---

# 10. Task 4：共享 MinerU API 适配器

## 目标

复用当前本机 MinerU 服务，不新装、不重造解析引擎。

## 文件

新建：

```text
backend/quantradar/research/parser/mineru.py
backend/quantradar/research/parser/quality.py
tests/unit/research/test_mineru.py
tests/unit/research/test_parse_quality.py
```

## 配置

```text
QUANTRADAR_MINERU_API_URL=http://127.0.0.1:58000
QUANTRADAR_MINERU_CONCURRENCY=1
QUANTRADAR_MINERU_TIMEOUT_SECONDS=...
```

## MVP 调用方式

为收敛复杂度：

> **MVP 只使用同步 `/file_parse` 链路。**

不实现 `/tasks` 异步队列客户端。

若后续实测同步模式无法满足长任务稳定性，再单独立项。

## 客户端必须保留

参考 OARadar 已验证行为，QuantRadar 内实现独立最小 Adapter：

- health check；
- timeout；
- 有限重试；
- ZIP 路径穿越防护；
- staging 解包；
- Markdown UTF-8 检查；
- 非空检查；
- 原子发布；
- parse quality。

不让 QuantRadar 运行时 import OARadar 项目代码，避免两个项目形成强耦合。

## Parse Quality

至少保存：

```text
char_count
replacement_char_ratio
table_count
image_count
quality_status
```

状态：

```text
PARSE_OK
PARSE_PARTIAL
PARSE_FAILED
```

只有 `PARSE_OK` 和允许配置的 `PARSE_PARTIAL` 才能进入 Agnes。

## 测试

```python
def test_mineru_health_check(): ...
def test_safe_zip_rejects_path_traversal(): ...
def test_parse_result_is_atomically_published(): ...
def test_empty_markdown_is_parse_failed(): ...
def test_quality_metrics_are_persisted(): ...
```

## 真实验收

使用 Gate 0 三份 PDF 重跑，结果与已验证产物在合理范围内一致。

## Commit

```text
feat(research): parse PDFs through shared MinerU API
```

---

# 11. Task 5：Agnes 分块全文分析

## 目标

实现 MVP 的核心价值：真正基于全文提炼研报，而不是标题摘要。

## 文件

新建：

```text
backend/quantradar/research/llm/base.py
backend/quantradar/research/llm/agnes.py
backend/quantradar/research/llm/chunking.py
backend/quantradar/research/llm/schemas.py
backend/quantradar/research/llm/prompts/market_report.md
backend/quantradar/research/llm/prompts/quant_report.md
tests/unit/research/test_chunking.py
tests/unit/research/test_agnes.py
tests/unit/research/test_analysis_merge.py
```

## Provider

正式业务只依赖：

```python
ResearchLLMProvider
```

MVP 只实现：

```text
AgnesProvider
```

不同时实现 OpenAI/Ollama Provider。

接口必须保留可替换性，但不要提前写未使用 Provider。

配置：

```text
QUANTRADAR_AGNES_API_KEY
QUANTRADAR_AGNES_BASE_URL
QUANTRADAR_AGNES_MODEL
QUANTRADAR_AGNES_MAX_INPUT_TOKENS
QUANTRADAR_AGNES_RPM
```

## 动态输入策略

```text
Source Markdown
       ↓
估算输入大小
       ↓
≤ 安全阈值
  → whole-report analysis

> 安全阈值
  → chunk planner
  → chunk analyses
  → report merge
```

不得直接截断。

## 分块规则

优先顺序：

1. MinerU 可确认的 page/section 边界；
2. Markdown 一级/二级标题；
3. 段落；
4. 最后才按 token/字符硬切。

只在需要时加少量 overlap。

每个 chunk 必须有稳定 `chunk_id`。

## 只做两套 Schema

### Market Schema

```text
one_line_summary
core_points
key_facts
new_information
why_it_matters
companies
catalysts
risks
research_value
evidence
```

### Quant Schema

```text
research_question
economic_logic
data
universe
signal
method
rebalance
backtest_period
benchmark
cost
main_results
robustness
bias_risks
reproducibility
research_value
follow_up_questions
evidence
```

MVP 评分只允许：

```text
HIGH
MEDIUM
LOW
```

不做 0–100 分。

## Evidence 最小契约

每条关键 evidence：

```json
{
  "chunk_id": "...",
  "page_start": 12,
  "page_end": 13
}
```

如果 MinerU 产物无法可靠给页码：

- 页码允许为空；
- 必须保留 `chunk_id`；
- 不得虚构页码。

对关键数字至少做最小自动检查：

- Evidence chunk 必须存在；
- 分析结果引用的关键数字应能在对应 source chunk 中找到或通过格式归一化找到；
- 校验失败记录 `EVIDENCE_MISMATCH`，不得静默忽略。

MVP 不做复杂语义 NLI 验证。

## 测试

```python
def test_short_report_uses_whole_report_path(): ...
def test_long_report_is_chunked_without_tail_truncation(): ...
def test_chunk_ids_are_stable(): ...
def test_merge_returns_valid_market_schema(): ...
def test_merge_returns_valid_quant_schema(): ...
def test_invalid_json_retries_then_fails_cleanly(): ...
def test_evidence_must_reference_existing_chunk(): ...
def test_numeric_evidence_mismatch_is_flagged(): ...
```

## 真实验收

Gate 0 三份报告必须全部重新通过：

- 短/长路径正确；
- 不发生尾部截断；
- 输出 JSON schema 合法；
- 人工检查核心结论与原文一致。

## Commit

```text
feat(research): analyze full reports with Agnes
```

---

# 12. Task 6：Daily Digest + 飞书 Outbox

## 目标

把全文分析结果变成每天真正可读的一份简报。

## 文件

新建：

```text
backend/quantradar/research/digest/builder.py
backend/quantradar/research/notify/feishu.py
tests/unit/research/test_digest.py
tests/unit/research/test_feishu.py
```

## Digest 只保留四部分

### A. Coverage

必须首先告诉用户今天处理了多少：

```text
热门研报：147
策略研究：38
金融工程：10

进入 PDF 全文候选：30
成功下载：29
MinerU 成功：29
Agnes 成功：28
非 PDF 未解析：9
```

### B. 市场风向

只做两类信息：

1. 基于全部元数据：
   - 栏目数量；
   - 高频行业；
   - 高频证券；
   - 标题高频关键词。

2. 基于“热门研报”已完成的结构化 Research Card：
   - 用一次 Agnes 日级汇总生成 3–5 条“昨日主要研究主题”。

不做：

- 看多/看空指数；
- 情绪评分；
- 热度因子；
- 预测收益。

### C. 热门研报精华

最多 5 篇。

优先依据：

```text
platform_order
+
research_value
```

不再发明复杂 score。

每篇只展示：

```text
标题
机构/作者
一句话结论
3 条核心观点
1–3 个关键数据
为什么值得看
```

### D. 策略 / 金融工程精选

最多 5 篇。

每篇只展示：

```text
标题
机构/作者
研究问题
方法
核心结果
主要风险/偏差
reproducibility
为什么值得 QuantRadar 后续关注
```

不生成回测任务。

## Digest 完整度

固定计算：

```text
analysis_completion =
analysis_success / pdf_candidate_count
```

状态：

```text
READY       >= 90%
PARTIAL     60%–89%
BLOCKED     < 60%
```

规则：

- READY：正常发日报；
- PARTIAL：允许发送，但顶部明确“部分报告未完成”；
- BLOCKED：不发送伪完整日报，只发送故障通知。

阈值配置化。

## Feishu Outbox

`notification_key`：

```text
research-digest:<target_date>:<digest_hash>
```

唯一约束。

发送流程：

```text
build digest
→ insert outbox PENDING
→ send Feishu
→ mark SENT
```

现有机器人关键词：

```text
QUANTRADAR_FEISHU_REQUIRED_KEYWORD
```

只负责在消息标题/正文中配置性加入。

MVP 目标是“应用层尽量防重复”，不声称外部接口具备绝对 exactly-once。

## 测试

```python
def test_digest_contains_coverage_first(): ...
def test_digest_limits_hot_and_quant_to_five_each(): ...
def test_partial_digest_is_explicitly_labeled(): ...
def test_blocked_digest_sends_failure_message_not_normal_digest(): ...
def test_same_notification_key_cannot_be_sent_twice_by_normal_flow(): ...
```

## Commit

```text
feat(research): build and send daily research digest
```

---

# 13. Task 7：最小 Research WebUI（标题清单核对页）

## 目标

给用户一个**可直接核对企业预警通采集结果是否正确**的最小页面。

本页的首要用途不是“研究阅读”，而是回答：

> **昨天三个栏目分别识别到了哪些标题？数量、顺序、栏目归属和处理状态是否正确？**

因此本 Task 是 MVP 的**可观测性与人工验收界面**，不是完整 Research Workbench。

## 后端文件

修改：

```text
backend/quantradar/api/app.py
```

新建测试：

```text
tests/unit/research/test_research_api.py
```

## 前端文件

修改：

```text
frontend/src/App.tsx
frontend/src/api.ts
```

新建：

```text
frontend/src/components/ResearchMVP.tsx
frontend/src/components/ResearchMVP.test.tsx
```

## 后端只读 API

只增加 3 个 GET 接口：

```text
GET /api/research/dates
GET /api/research/reports?date=YYYY-MM-DD&channel=HOT|STRATEGY|FINANCIAL_ENGINEERING
GET /api/research/status?date=YYYY-MM-DD
```

### `/api/research/dates`

返回已有采集日期，最近日期优先。

### `/api/research/reports`

每条只返回核对所需字段：

```json
{
  "source_report_id": "...",
  "title": "...",
  "institution": "...",
  "authors": ["..."],
  "publish_date": "2026-08-24",
  "channel": "HOT",
  "platform_order": 1,
  "content_type": "pdf",
  "pdf_status": "SUCCESS",
  "parse_status": "SUCCESS",
  "analysis_status": "SUCCESS"
}
```

要求：

- 默认按 `platform_order ASC`；
- 不在 API 中做二次推荐或评分；
- 不返回 PDF 二进制；
- 不开放文件系统路径；
- 不增加写操作 API。

### `/api/research/status`

返回当日汇总：

```text
三个栏目各自采集数量
唯一报告数
PDF 数量
unsupported_content 数量
下载成功/失败
MinerU 成功/失败
Agnes 成功/失败
Digest 状态
Feishu 状态
最近一次 pipeline run 状态
```

## 页面结构

QuantRadar 左侧菜单新增：

```text
Research
```

页面只包含四块：

### A. 日期选择

默认最近一个已采集日期。

### B. 三栏目 Tab

```text
热门研报（147）
策略研究（38）
金融工程（10）
```

### C. 标题清单

表格字段固定：

```text
顺序
标题
机构
作者
source_report_id
内容类型
PDF
MinerU
Agnes
```

其中：

- “顺序”直接显示 `platform_order`；
- 标题必须完整显示，允许换行；
- `source_report_id` 可复制；
- 同一报告出现在不同栏目时，各栏目均可看到，但数据库仍只有一个 report 本体；
- 非 PDF 显示 `unsupported_content`；
- 不在列表中显示 AI 评分。

### D. 当日流水线状态

只显示：

```text
采集
PDF
MinerU
Agnes
Digest
Feishu
```

以及成功/失败/待处理数量。

## 明确不做

本 Research WebUI **不做**：

- PDF 在线阅读器；
- Markdown 在线阅读器；
- Agnes 全文 Research Card 页面；
- 搜索全历史研报；
- 收藏；
- 点赞；
- 人工打分；
- 编辑标签；
- 重跑按钮；
- 下载按钮；
- Hypothesis 按钮；
- 回测按钮；
- 图表；
- 研究知识库；
- 分析师详情页。

如果标题清单和状态页能满足人工验收，本 Task 即结束。

## 测试

后端：

```python
def test_reports_api_returns_channel_ordered_titles(): ...
def test_reports_api_filters_by_date_and_channel(): ...
def test_reports_api_exposes_unsupported_content_without_failure(): ...
def test_status_api_counts_pipeline_states(): ...
```

前端：

```typescript
it("默认展示最近采集日期", async () => {});
it("三个栏目显示正确数量", async () => {});
it("标题按 platform_order 展示", async () => {});
it("切换栏目后只显示该栏目标题", async () => {});
it("非 PDF 显示 unsupported_content", async () => {});
it("显示 PDF/MinerU/Agnes 处理状态", async () => {});
```

## 真实验收

使用 Gate 0 的 `2026-08-24` 数据：

WebUI 必须显示：

```text
热门研报：147
策略研究：38
金融工程：10
```

并分别抽查至少 20 条：

```text
WebUI 标题
vs
数据库记录
vs
企业预警通真实页面/采集快照
```

要求：

- 标题一致；
- source_report_id 一致；
- platform_order 一致；
- 栏目归属一致。

该真实核对通过后，才视为 Collector 的最终人工可见验收完成。

## Commit

```text
feat(research): add minimal report verification WebUI
```

---

# 14. Task 8：CLI、断点续跑与 systemd

## 目标

把上述模块组装成一个独立、可无人值守运行的生产任务。

## 文件

新建：

```text
backend/quantradar/research/cli.py
backend/quantradar/research/pipeline.py
deploy/systemd/quantradar-research.service
deploy/systemd/quantradar-research.timer
tests/unit/research/test_pipeline.py
tests/integration/research/test_daily_pipeline.py
```

如仓库没有 `deploy/systemd/`，只新增这一层，不顺手重构现有部署结构。

## CLI

只提供必要命令：

```bash
python -m quantradar.research.cli health

python -m quantradar.research.cli collect \
  --date 2026-08-24

python -m quantradar.research.cli daily \
  --date 2026-08-24

python -m quantradar.research.cli resend \
  --date 2026-08-24
```

不拆出十几个维护命令。

`daily` 固定顺序：

```text
COLLECT
→ SELECT CANDIDATES
→ DOWNLOAD
→ PARSE
→ ANALYZE
→ BUILD DIGEST
→ NOTIFY
```

## 断点续跑

重复执行同一日期时：

```text
metadata 已存在 → upsert/snapshot
PDF hash 已成功 → skip
Markdown 同输入 hash 已成功 → skip
Analysis input_hash + model + prompt_version 未变 → skip
同 digest_hash 已发送 → skip
```

失败任务只重跑失败阶段，不主动重做已经成功的重型任务。

## systemd

只启一个每日 timer。

建议默认：

```text
00:30 开始处理前一自然日
```

发送时间不再单独设第二个调度器：

> pipeline 完成后直接发送飞书。

这样避免“解析还没完成但 07:00 强制发送半成品”的第二套时序状态机。

必须配置：

```text
Persistent=true
```

机器错过 00:30 后启动时可以补跑。

Research systemd service 与 QuantRadar FastAPI 完全独立。

## 测试

```python
def test_daily_pipeline_skips_successful_stages_on_rerun(): ...
def test_one_report_failure_does_not_stop_other_reports(): ...
def test_blocked_auth_stops_before_download(): ...
def test_pipeline_builds_partial_digest_when_threshold_allows(): ...
def test_rerun_does_not_duplicate_feishu_outbox(): ...
```

## Commit

```text
feat(research): run daily pipeline as standalone service
```

---

# 15. Task 9：只做验收，不加新功能

这一阶段禁止继续写产品功能。

## Gate A：30 份样本

样本至少覆盖：

```text
热门研报         10
策略研究         10
金融工程/量化    10
```

并尽量覆盖：

- 短 PDF；
- 长 PDF；
- 双栏；
- 表格；
- 多图表；
- 扫描页；
- 公式较多的金融工程研报。

人工对照：

```text
PDF
vs
Source Markdown
vs
Agnes JSON
```

重点记录：

- Markdown 丢段；
- 乱码；
- 表格错位；
- 长报告尾部丢失；
- Agnes 错误数字；
- Agnes 错误理解作者结论；
- Evidence 不可回溯。

任何严重问题必须修复现有链路，不增加新功能。

## Gate B：3 个历史日期

选择 3 个真实日期跑完整：

```text
企业预警通
→ PostgreSQL
→ PDF
→ MinerU
→ Agnes
→ Digest
→ 飞书测试
```

验收：

- 三栏目数量与页面抽查一致；
- 无明显分页遗漏；
- source_report_id 无重复污染；
- platform_order 保留；
- 非 PDF 被正确标记；
- 飞书 Coverage 与数据库一致。

## Gate C：连续 7 天无人值守

连续 7 天由 systemd 自动运行。

每日记录：

```text
collection_count
candidate_count
download_success
parse_success
analysis_success
unsupported_count
digest_status
feishu_status
elapsed_seconds
```

7 天期间：

- 人工不得每天手动补跑；
- 登录失效可人工重新登录，但系统必须先正确告警；
- 单篇失败不得拖垮整日；
- 重启后不得重复处理全部成功任务；
- 不得出现明显重复飞书。

---

# 16. 最终 MVP PASS 门禁

只有以下条件同时满足，才能写入：

```text
QUANTRADAR_RESEARCH_MVP_PASS
```

## Collection

- [ ] 三栏目真实采集通过；
- [ ] `source_report_id` 唯一键稳定；
- [ ] `publishDate` 日期正确；
- [ ] `size/from` 分页完整；
- [ ] `platform_order` 快照正确；
- [ ] 同报告跨栏目不重复建 report。

## Artifact

- [ ] PDF 下载成功率 ≥ 95%；
- [ ] SHA256 稳定；
- [ ] PDF 页数由 PDF 专用工具确认；
- [ ] 非 PDF 正确进入 `unsupported_content`；
- [ ] MinerU 对可解析 PDF 成功率 ≥ 95%。

## Intelligence

- [ ] 长报告没有因单次上下文限制被截断；
- [ ] Market / Quant 两套 Schema 稳定；
- [ ] 30 份人工样本无严重事实幻觉；
- [ ] Evidence 引用的 chunk 均存在；
- [ ] 关键数字 Evidence mismatch 能被发现。

## WebUI Verification

- [ ] WebUI 可选择已采集日期；
- [ ] 三栏目数量与数据库一致；
- [ ] 标题按 `platform_order` 正确展示；
- [ ] `source_report_id`、栏目归属、内容类型正确；
- [ ] 可看到 PDF / MinerU / Agnes / Digest / Feishu 状态；
- [ ] Gate 0 日期至少每栏目抽查 20 条标题通过。

## Production

- [ ] 3 个历史日期全链路 PASS；
- [ ] 连续 7 天无人值守 PASS；
- [ ] 任务可重复执行且不重复下载/解析/分析成功任务；
- [ ] 飞书正常流程无明显重复；
- [ ] PARTIAL / BLOCKED 不伪装 SUCCESS；
- [ ] 登录失效等关键错误能够告警；
- [ ] Research 任务不影响 FastAPI / BulletTrade / Kronos。

---

# 17. 本阶段允许修改的仓库范围

原则上只允许：

```text
backend/quantradar/research/**
tests/unit/research/**
tests/integration/research/**
tests/fixtures/research/**
deploy/systemd/**
backend/quantradar/api/app.py        # 仅新增 Research 只读 API
frontend/src/App.tsx                 # 仅增加 Research 菜单入口
frontend/src/api.ts                  # 仅增加 Research 查询 API client
frontend/src/components/ResearchMVP.tsx
frontend/src/components/ResearchMVP.test.tsx
pyproject.toml
requirements*.txt        # 仅依项目当前依赖管理规范同步
.env.example
docs/RESEARCH_MVP_IMPLEMENTATION_PLAN.md
.gitignore               # 仅在确有本地 Research 产物进入仓库风险时修改
```

除非测试证明必要，不修改：

```text
backend/quantradar/storage.py
backend/quantradar/worker.py
backend/quantradar/backtest*
backend/quantradar/kronos/**
backend/quantradar/api/**          # 除 app.py 中最小 Research GET API 外
frontend/**                           # 除本计划列明的 Research MVP 文件外
vendor/bullet-trade/**
```

这条边界用于防止 MVP 开发再次发散。

---

# 18. 推荐提交顺序

严格按以下顺序：

```text
1. feat(research): add MVP storage and config
2. feat(research): collect qyj report metadata
3. feat(research): download and register PDF artifacts
4. feat(research): parse PDFs through shared MinerU API
5. feat(research): analyze full reports with Agnes
6. feat(research): build and send daily research digest
7. feat(research): add minimal report verification WebUI
8. feat(research): run daily pipeline as standalone service
9. test(research): validate MVP on real report pipeline
```

不并行开发前端，不并行开发 Hypothesis，不并行开发新的量化功能。

---

# 19. Stop Conditions

出现以下任一情况时停止扩展并先修复：

1. 企业预警通分页结果与人工抽查明显不一致；
2. `source_report_id` 出现无法解释的复用；
3. PDF 下载内容与报告不对应；
4. MinerU 大量低质量但被误判成功；
5. 长报告分析出现尾部丢失；
6. Agnes 输出关键数字无法回到 Source Markdown；
7. 同一日期反复执行会重复发飞书；
8. Research 任务影响现有回测/Kronos 进程；
9. 为解决单点问题需要引入 Celery/Redis/新的数据库/新的前端框架；
10. 开发过程中出现“顺便把 Research WebUI / Hypothesis / 回测也一起做了”的范围扩张。

这些情况都不允许通过新增功能绕过。

---

# 20. 本计划完成后的系统形态

MVP 完成后，QuantRadar 只新增这一项能力：

```text
每天夜间

企业预警通
├─ 热门研报
├─ 策略研究
└─ 金融工程
      ↓
全部元数据归档
      ↓
Research WebUI
（核对标题/顺序/状态）
      ↓
最多 30 篇 PDF 全文候选
      ↓
MinerU
      ↓
Agnes 2.5
      ↓
Research Cards
      ↓
Daily Digest
      ↓
飞书
```

到这里停止。

下一阶段是否做：

```text
完整 Research Workbench
PDF/Markdown 在线阅读
知识库
分析师追踪
Hypothesis
QuantRadar 自动回测
```

必须等 `QUANTRADAR_RESEARCH_MVP_PASS` 后重新立项，不属于本开发计划。
