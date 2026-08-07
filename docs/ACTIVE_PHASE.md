# QuantRadar 当前开发任务

文件：`docs/ACTIVE_PHASE.md`

**当前阶段：Phase 8 — 中文 WebUI 雏形（消费 FastAPI）**

```text
上一阶段 Phase 7 已完成（FASTAPI_CORE_PASS）：
  - backend/quantradar/api/app.py 暴露 /api/health、/api/price、/api/backtest、/api/snapshot
  - 全程经 InvestmentDataProvider 读真实数据，无 mock；TestClient 测试全过
本阶段做 Phase 8（中文 WebUI 雏形）；完成后评估是否进入 Phase 9（PostgreSQL / Worker）。
```

---

# 一、目标

在 FastAPI 之上提供一个**最小但真实**的中文单页前端，消费已有接口：
查询真实行情、触发真实回测、查看可复现快照指纹。验证「前端 + API + 真实数据」链路打通。

```text
数据正确性 > API > WebUI。前端仅消费 API，不直连数据库；禁止 mock。
```

---

# 二、范围与边界（强制）

```text
允许：
  - backend/quantradar/api/static/index.html（中文界面）：行情查询表单、回测触发、
    快照结果展示；通过 fetch 调用 /api/price、/api/backtest、/api/snapshot。
  - 在 app.py 增加 GET / 返回该静态页（StaticFiles 或 HTMLResponse）。
  - 补齐 tests/unit/test_webui.py：GET / 返回 200 且含中文标题与 API 引用；
    关键交互路径（行情查询）经 API 端到端验证（前端 fetch 由 API 测试间接覆盖）。

禁止：
  - 改动 BulletTrade 核心。
  - 写入 investment_data。
  - 引入前端构建工具链（React/Vite 等）；保持单静态 HTML（Phase 9 前不引入）。
  - 提前进入 PostgreSQL / Worker / Qlib / ETF / QMT / 实盘（除非本阶段需要）。
```

---

# 三、兼容契约

```text
- 前端所有数据来自 /api/*；不在前端内嵌任何价格/复权逻辑。
- 中文文案；字段名沿用 JoinQuant（open/high/low/close/volume/amount/money）。
```

---

# 四、测试

至少覆盖：

```text
- GET / 返回 200，页面含中文标题与对 /api/price、/api/backtest 的引用。
- 回测触发路径端到端：前端 fetch /api/backtest 返回可复现 fingerprint（复用 test_api 逻辑）。
- QuantRadar 全量测试 + BulletTrade registry 回归保持全过。
```

运行：

```text
tests/unit （pytest）
vendor/bullet-trade/tests/unit/test_provider_registry.py （回归）
```

---

# 五、验收

完成标志：`WEBUI_CORE_PASS`

```text
[PASS] GET / 返回中文单页（含行情查询 / 回测 / 快照展示）
[PASS] 前端经 /api/backtest 触发真实回测并展示可复现指纹
[PASS] 数据全部来自 API（无前端内嵌价格逻辑、无 mock）
[PASS] 补充 tests/unit/test_webui.py 并全过；registry 回归 + 全量测试保持全过
[PASS] 单一 commit 含 WEBUI_CORE_PASS
```

---

# 六、结束条件

```text
1. 实现中文 WebUI 雏形（静态页 + GET /）+ 测试
2. 更新 docs/CURRENT_STATE.md（WebUI PASS）
3. git diff --check 无遗留空白错误
4. 单一 commit（WEBUI_CORE_PASS）
5. push origin main
6. 将 ACTIVE_PHASE 改为 Phase 9（PostgreSQL / Worker，按需）-> 自动进入 Phase 9
```
