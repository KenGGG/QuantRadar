# QuantRadar Makefile —— 本地 A 股量化研究平台
#
# 目标：
#   make setup    安装依赖（BulletTrade 基线 editable + 本项目 + 测试依赖）
#   make test     运行全部单元测试（pytest tests/unit）
#   make smoke    端到端冒烟（数据→回测→快照→API→Web 入口；脚本 scripts/smoke.py）
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

.PHONY: setup test smoke dev install-hooks help

help:
	@echo "QuantRadar 可用目标："
	@echo "  make setup   安装依赖（BulletTrade editable + 本项目 + 运行时/测试依赖 + 前端构建）"
	@echo "  make test    运行单元测试"
	@echo "  make smoke   端到端冒烟测试"
	@echo "  make dev     启动开发服务器 (http://127.0.0.1:7231)"

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

dev:
	$(PYTHON) -m uvicorn quantradar.api.app:app --host 127.0.0.1 --port 7231 --reload

test:
	$(PYTHON) -m pytest tests/unit -q

smoke:
	$(PYTHON) scripts/smoke.py

dev:
	$(PYTHON) -m uvicorn quantradar.api.app:app --host 127.0.0.1 --port 7231 --reload
