# QuantRadar

基于**本地真实数据、可审计、可复现**的 A 股量化研究与回测平台。

核心理念：以 [investment_data](https://github.com/chenditc/investment_data)（Dolt 只读事实源）为唯一数据真相，回测核心复用项目内 `vendor/bullet-trade` 的撮合/账户/组合会计，所有实验结果通过 Snapshot 指纹固化，保证可复现、防未来函数。

> 状态：**QUANTRADAR_FUNCTIONAL_V1_PASS ✅**（功能型 V1 达成；严谨研究型 V1 加固进行中，见 docs/ACTIVE_PHASE.md）

---

## 一、能力矩阵（功能型 V1）

> 状态：**QUANTRADAR_FUNCTIONAL_V1_PASS ✅**（功能闭环可用）。原 `QUANTRADAR_V1_PASS` 已降级为
> 功能型——严谨研究型 V1（数据层完整性、复权口径统一、多模型/参数寻优、样本外稳健性）尚待后续阶段。

| 标志 | 含义 |
|------|------|
| `FULL_AUDIT_REPRO_PASS` | 完整 Snapshot / Audit（Dolt HEAD、schema 哈希、结果指纹、确定性测试） |
| `PERSIST_WORKER_PASS` | PostgreSQL + 异步回测 Worker 落库 |
| `WEB_WORKBENCH_PASS` | 正式 React WebUI 工作台（AntD + Monaco + ECharts） |
| `QLIB_BULLETTRADE_LOOP_PASS` | Qlib 最小闭环（Alpha158 + LightGBM → Target Weight → BulletTrade 回测） |
| `QUANTRADAR_SMOKE_PASS` | 全链路冒烟（`make smoke` EXIT 0：数据→回测→快照→API→Web 入口） |

### Hardening 加固（已全绿）

| 标志 | 含义 |
|------|------|
| `HARDENING_DEPS_PASS` | 依赖可重建（`pyproject` + 干净 `requirements.txt` + `make setup` 装前端 + 前端依赖补全） |
| `HARDENING_TEST_ISOLATION_PASS` | 测试仅用 `_test` 库；`drop_all` 拒绝非 `_test` 库；`0.0.0.0` 强警告 |
| `HARDENING_AUDIT_CHAIN_PASS` | snapshot config 完整 + 策略源码落库 + `run_id/snapshot_hash/result_hash` 语义分明 |
| `HARDENING_QLIB_NOFUTURE_PASS` | bridge 同日前视修复 + Train/Valid/Test 不重叠守卫 + 复权训练 |
| `HARDENING_WORKER_CI_PASS` | Worker 固定线程池 + 重启恢复 + GitHub Actions CI |

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
| **PostgreSQL** | 异步回测落库（本机专用库，如 `quantradar`）；**必须**在 `.env` 设置 `QUANT_RADAR_PG_URL`（格式见 `.env.example`），否则 `/api/backtest/async` 等返回 503。`quantradar.sh` 启动会自动加载 `.env` 并导出该变量 | 用户本地数据库 |

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
  > ⚠️ **安全边界**：`QUANTRADAR_HOST=0.0.0.0` 会把应用暴露到所有网络接口。`/api/backtest/strategy`
  > 接受任意策略源码并在本进程内执行（**无认证、等价于远程代码执行**）。仅限本机可信研究使用；
  > 共享/LAN/公网环境请保持默认 `127.0.0.1` 并在前面加鉴权网关。`quantradar.sh` 在检测到 `0.0.0.0` 时会强警告。
- 启动前会预检 Dolt(3307) 可达性；不可达仅**警告**不阻断（避免误杀）。
- 端口冲突时 uvicorn 会退出，脚本报“启动失败”并指向日志，请用上面的端口变量换端口。

启动后访问：

- Web 工作台：<http://127.0.0.1:7231/>
- 健康检查：<http://127.0.0.1:7231/api/health>

---

## 五、开发命令（Makefile）

```bash
make setup      # 安装依赖（BulletTrade editable + 本项目 + 测试依赖 + 前端构建）
make test       # 运行单元测试（pytest tests/unit；PG 集成测试需 QUANT_RADAR_TEST_PG_URL 指向 `_test` 库）
make smoke      # 端到端冒烟（scripts/smoke.py，全链路）
make dev        # 开发服务器（uvicorn --reload，等价于 start 的 reload 版）
```

> 集成测试安全隔离：PG 相关测试仅当 `QUANT_RADAR_TEST_PG_URL` 指向**库名含 `_test`** 的专用库时才运行，
> 否则整文件 skip；`drop_all` 对任何非 `_test` 库名拒绝执行。切勿将正式 `QUANT_RADAR_PG_URL` 用于测试。

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
- **安全**：`/api/backtest/strategy` 为无认证代码执行接口，默认仅绑 `127.0.0.1`，禁止暴露到 LAN/公网。
- **测试隔离**：集成测试仅连接 `QUANT_RADAR_TEST_PG_URL` 指向的 `_test` 库，`storage.drop_all` 拒绝任何非 `_test` 库名，杜绝误 DROP 正式库。
- 任意回测结果均以 Snapshot 指纹固化，相同配置应可复现；若指纹变化说明配置/数据/代码有变。
- 后续（Phase 10，非 V1 范围）：Qlib 高级研究、多模型、参数寻优；ETF / QMT / 实盘为 BLOCKED。
