# QuantRadar Makefile —— 本地 A 股量化研究平台
#
# 目标：
#   make setup    安装依赖（BulletTrade 基线 editable + 本项目 + 测试依赖）
#   make test     运行全部单元测试（pytest tests/unit）
#   make smoke    端到端冒烟（数据→回测→快照→API→Web 入口；脚本 scripts/smoke.py）
#   make research 研究链路端到端（Qlib 构建→grid 选优+walk-forward OOS→可复现报告；脚本 scripts/research_oos.py）
#   make dev      启动 FastAPI 开发服务器（uvicorn）
#
# 说明：
#   - investment_data（Dolt 3307）为只读事实源，需本地可达。
#   - 所有步骤均基于真实数据，无 mock。
#   - 推送因环境 TLS 阻断时由用户侧执行 `git push origin main`。

PYTHON ?= .venv/bin/python
PIP    ?= .venv/bin/pip
NPM    ?= npm
VENV   ?= .venv

.PHONY: setup test smoke research kronos-data-audit kronos-runtime-setup kronos-gpu-smoke kronos-research-pipeline dev install-hooks help

help:
	@echo "QuantRadar 可用目标："
	@echo "  make setup      安装依赖（BulletTrade editable + 本项目 + 运行时/测试依赖 + 前端构建）"
	@echo "  make test       运行单元测试"
	@echo "  make smoke      端到端核心冒烟测试（数据→回测→快照→API→Web）"
	@echo "  make research   研究链路端到端（Qlib 构建→网格+OOS 可复现报告，需 Dolt+qlib）"
	@echo "  make kronos-data-audit  只读执行 Kronos Goal 0 数据事实审计"
	@echo "  make kronos-runtime-setup  安装并锁定独立 Kronos-base CUDA 运行时"
	@echo "  make kronos-gpu-smoke  执行 Kronos Goal 1 真实 GPU 分级基准"
	@echo "  make kronos-research-pipeline START=2022-06-24 END=2022-07-01  执行 Goal 2 研究闭环"
	@echo "  make dev        启动开发服务器 (http://127.0.0.1:7231)"

setup:
	python3 -m venv $(VENV) || true
	$(PIP) install --upgrade pip
	# BulletTrade 基线（editable，源码在 vendor/ 下）
	$(PIP) install -e ./vendor/bullet-trade
	# 本项目（quantradar）及其依赖（依赖见 pyproject.toml [project.dependencies]）
	$(PIP) install -e .
	# 测试依赖 + 运行时依赖（干净可复现；不含本机绝对路径）
	$(PIP) install -r requirements.txt
	# 前端依赖与构建（React+TS+Vite+AntD+Monaco+ECharts）
	cd frontend && $(NPM) ci && $(NPM) run build

test:
	$(PYTHON) -m pytest tests/unit -q

smoke:
	$(PYTHON) scripts/smoke.py

research:
	$(PYTHON) scripts/research_oos.py --build \
		--start 2020-01-01 --end 2022-12-31 --max-instruments 50 \
		--train-years 2 --valid-months 6 --test-months 6 --step-months 6 \
		--num-boost-round 50 --early-stopping-rounds 10 \
		--out reports/oos

kronos-data-audit:
	PYTHONPATH=backend $(PYTHON) scripts/kronos_data_audit.py

kronos-runtime-setup:
	PYTHONPATH=backend $(PYTHON) scripts/setup_kronos_runtime.py

kronos-gpu-smoke:
	PYTHONPATH=backend $(PYTHON) scripts/kronos_gpu_smoke.py

kronos-research-pipeline:
	PYTHONPATH=backend $(PYTHON) scripts/kronos_research_pipeline.py \
		--start $(START) --end $(END) --topk $(or $(TOPK),20)

dev:
	$(PYTHON) -m uvicorn quantradar.api.app:app --host 127.0.0.1 --port 7231 --reload
