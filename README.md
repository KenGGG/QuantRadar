# QuantRadar

基于**本地真实数据、可审计、可复现**的 A 股量化研究与回测平台。

核心理念：以 [investment_data](https://github.com/chenditc/investment_data)（Dolt 只读事实源）为唯一数据真相，回测核心复用项目内 `vendor/bullet-trade` 的撮合/账户/组合会计，所有实验结果通过 Snapshot 指纹固化，保证可复现、防未来函数。

> 状态：**QUANTRADAR_V1_PASS ✅**（Closing Phase 收官，5 项标志全绿）

---

## 一、能力矩阵（V1）

| 标志 | 含义 |
|------|------|
| `FULL_AUDIT_REPRO_PASS` | 完整 Snapshot / Audit（Dolt HEAD、schema 哈希、结果指纹、确定性测试） |
| `PERSIST_WORKER_PASS` | PostgreSQL + 异步回测 Worker 落库 |
| `WEB_WORKBENCH_PASS` | 正式 React WebUI 工作台（AntD + Monaco + ECharts） |
| `QLIB_BULLETTRADE_LOOP_PASS` | Qlib 最小闭环（Alpha158 + LightGBM → Target Weight → BulletTrade 回测） |
| `QUANTRADAR_SMOKE_PASS` | 全链路冒烟（`make smoke` EXIT 0：数据→回测→快照→API→Web 入口） |

---

## 二、架构与关键路径

```text
investment_data (Dolt SQL server, 127.0.0.1:3307, 只读事实源)
→ InvestmentDataProvider        (backend/quantradar/providers, 实现 DataProvider ABC)
→ BulletTrade 回测引擎          (撮合 / 账户 / 订单 / 成交 / 调度，不重实现)
→ Snapshot / 可复现指纹         (backend/quantradar/snapshot.py + audit.py)
→ FastAPI (quantradar.api.app)  (/api/health, /api/price, /api/backtest, /api/backtest/strategy, 异步 + 实验)
→ 前端工作台 (frontend/dist)    (React+TS+Vite+AntD+Monaco+ECharts，由 FastAPI 托管 GET /)
→ Qlib 最小闭环 (可选研究)       (backend/quantradar/qml: dump→Alpha158/LightGBM→TopK Target Weight→BulletTrade)
→ PostgreSQL + Worker           (异步回测落库, backend/quantradar/storage.py + worker.py)
```

**整个运行时只需一个进程**：`uvicorn quantradar.api.app:app`。
前端是静态产物由 FastAPI 托管；异步回测 Worker 以 daemon 线程运行在该进程内。

---

## 三、依赖（启动前需就绪）

| 依赖 | 说明 | 由谁管理 |
|------|------|----------|
| Python 3 虚拟环境 `.venv` | 项目依赖（BulletTrade、qlib、fastapi、lightgbm 等） | `make setup` |
| **investment_data (Dolt 3307)** | 只读行情事实源，**必须本机可达** | 用户本地启动 Dolt |
| **PostgreSQL** | 异步回测落库（本机专用库，如 `quantradar`） | 用户本地数据库 |

> 本仓库**不**管理 Dolt / PostgreSQL 的启停，只在使用时读取。`.env`（复制自 `.env.example`）配置 Dolt 连接；PostgreSQL 连接串见 `backend/quantradar/storage.py`。

---

## 四、一键启停（推荐）

根目录提供 `quantradar.sh` 管理启动 / 重启 / 关闭：

```bash
chmod +x quantradar.sh        # 首次需赋可执行权限（已默认提交）

./quantradar.sh start         # 启动（后台，写 logs/quantradar.pid + logs/quantradar.log）
./quantradar.sh stop          # 优雅停止；超时(~10s)则 SIGKILL
./quantradar.sh restart       # stop + start
./quantradar.sh status        # 查看运行状态与访问地址
```

- 默认监听 `127.0.0.1:7231`。可用环境变量覆盖：
  ```bash
  QUANTRADAR_HOST=0.0.0.0 QUANTRADAR_PORT=8010 ./quantradar.sh start
  ```
- 启动前会预检 Dolt(3307) 可达性；不可达仅**警告**不阻断（避免误杀）。
- 端口冲突时 uvicorn 会退出，脚本报“启动失败”并指向日志，请用上面的端口变量换端口。

启动后访问：

- Web 工作台：<http://127.0.0.1:7231/>
- 健康检查：<http://127.0.0.1:7231/api/health>

---

## 五、开发命令（Makefile）

```bash
make setup      # 安装依赖（BulletTrade editable + 本项目 + 测试依赖）
make test       # 运行单元测试（pytest tests/unit）
make smoke      # 端到端冒烟（scripts/smoke.py，全链路）
make dev        # 开发服务器（uvicorn --reload，等价于 start 的 reload 版）
```

---

## 六、目录速览

```text
backend/quantradar/   后端核心（provider / backtest / snapshot / audit / worker / storage / qml / api）
frontend/             React+TS+Vite 工作台（npm run build -> dist，由 GET / 托管）
docs/                 阶段文档（CURRENT_STATE.md / ACTIVE_PHASE.md / 00~06 规范）
scripts/smoke.py      全链路冒烟
quantradar.sh         一键启停脚本（本文件同目录）
logs/                 运行时日志（quantradar.log / quantradar.pid）
```

---

## 七、注意事项

- **禁止**向仓库写入 investment_data 的写操作（只读事实源）。
- **禁止**用 Qlib 替换 BulletTrade 撮合与组合会计；Qlib 仅用于因子研究 / 模型 / 预测。
- 任意回测结果均以 Snapshot 指纹固化，相同配置应可复现；若指纹变化说明配置/数据/代码有变。
- 后续（Phase 10，非 V1 范围）：Qlib 高级研究、多模型、参数寻优；ETF / QMT / 实盘为 BLOCKED。
