# Auto YOLO Training · Makefile
#
# 跨平台支持：
#   - Linux/macOS：直接 `make <target>`
#   - Windows：需要 GnuWin32 make 或 Git Bash 自带 make
#
# 常用目标：
#   make help           - 显示所有目标
#   make install        - 安装依赖（含 dev）
#   make test           - 跑 CPU-safe 测试
#   make lint           - ruff 检查
#   make smoke          - 烟雾训练验证（_smoke_test 数据集）
#   make gpu-smoke      - GPU 通道验收（真跑一次 CUDA 训练）
#   make frontend-dev   - 启动前端开发服务器（Vite，含 API 代理）
#   make frontend-build - 构建前端产物（frontend/dist）
#   make frontend-check - 构建前端并校验产物预算
#   make docs           - 本地启动 MkDocs 预览
#   make docker-build   - 构建 CPU Docker 镜像
#   make docker-run     - 启动 Gradio 容器

# ---------- 配置 ----------
PYTHON ?= python
PIP ?= pip
PNPM ?= pnpm
DOCKER_IMAGE ?= ayt
DOCKER_TAG ?= cpu
DOCKER_REGISTRY ?= ""

# 颜色（终端支持 ANSI 时显示）
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
RESET := \033[0m

# 默认目标
.DEFAULT_GOAL := help

.PHONY: help
help:  ## 显示所有可用目标
	@echo "$(GREEN)Auto YOLO Training · Makefile$(RESET)"
	@echo ""
	@echo "用法："
	@echo "  make <target>"
	@echo ""
	@echo "可用目标："
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	 awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'

# ---------- 安装 ----------
.PHONY: install
install:  ## 安装运行时 + 开发依赖
	$(PIP) install -e ".[dev]"

.PHONY: install-cpu
install-cpu:  ## 安装 CPU 版 PyTorch（仅 CPU 机器）
	$(PIP) install --index-url https://download.pytorch.org/whl/cpu torch torchvision
	$(PIP) install -e ".[dev]"

.PHONY: install-gpu
install-gpu:  ## 安装 cu128 GPU PyTorch（NVIDIA 机器）
	$(PIP) install --index-url https://download.pytorch.org/whl/cu128 torch torchvision
	$(PIP) install -e ".[dev]"

# ---------- 测试 ----------
.PHONY: test
test:  ## 跑 CPU-safe 测试套件
	$(PYTHON) -m pytest -m "not gpu and not training" -v --tb=short

.PHONY: test-all
test-all:  ## 跑全部测试（含标记为 gpu/training 的，跳过实际 GPU 训练）
	$(PYTHON) -m pytest -v --tb=short -m "not gpu"

.PHONY: test-cov
test-cov:  ## 跑测试 + 生成 coverage 报告（html + 终端）
	$(PYTHON) -m pytest -m "not gpu and not training" --cov=src --cov-report=html --cov-report=term

.PHONY: test-cov-gate
test-cov-gate:  ## 覆盖率门禁（CI 同款：地板 69%，基线 70%）
	$(PYTHON) -m pytest -m "not gpu and not training" \
	 --cov=src --cov-report=term-missing:skip-covered --cov-fail-under=69

.PHONY: audit
audit:  ## 依赖安全审计（pip-audit；本地看全量，CI 的忽略清单见 .github/workflows/audit.yml）
	$(PYTHON) -m pip_audit --skip-editable --format columns

# ---------- Lint / 格式 ----------
.PHONY: lint
lint:  ## ruff 检查
	$(PYTHON) -m ruff check .

.PHONY: lint-fix
lint-fix:  ## ruff 自动修复
	$(PYTHON) -m ruff check --fix .

.PHONY: format
format:  ## ruff 自动格式化
	$(PYTHON) -m ruff format .

.PHONY: format-check
format-check:  ## 仅检查格式不修改
	$(PYTHON) -m ruff format --check .

.PHONY: typecheck
typecheck:  ## mypy 静态类型检查（可选，慢）
	$(PYTHON) -m mypy src/

# ---------- 烟雾验证 ----------
.PHONY: smoke
smoke:  ## 跑烟雾训练（_smoke_test 数据集，CPU 1 epoch）
	$(PYTHON) train.py _smoke_test --model yolov8n.pt --imgsz 64 --batch 2 --epochs 1 --skip-validation --override device=

.PHONY: smoke-validate
smoke-validate:  ## 烟雾数据校验
	$(PYTHON) validate_data.py _smoke_test

.PHONY: gpu-smoke
gpu-smoke:  ## GPU 通道验收（真跑一次 CUDA 训练 + 标记用例；需本机有 NVIDIA GPU）
	$(PYTHON) -m pytest -m gpu -v --tb=short
	$(PYTHON) scripts/gpu_smoke.py

.PHONY: gpu-check
gpu-check:  ## 只做 GPU 环境/kernel 检查（秒级，不跑训练）
	$(PYTHON) scripts/gpu_smoke.py --skip-training

.PHONY: tensorboard
tensorboard:  ## 启动 TensorBoard 查看训练曲线（runs/ 目录）
	$(PYTHON) -m tensorboard.main --logdir runs

# ---------- 前端（Vue SPA，frontend/）----------
# 前端是控制台的主界面；Gradio 那套已冻结，仅作历史入口保留。
.PHONY: frontend-install
frontend-install:  ## 安装前端依赖（pnpm，严格按 lockfile）
	cd frontend && $(PNPM) install --frozen-lockfile

.PHONY: frontend-dev
frontend-dev:  ## 启动前端开发服务器（http://127.0.0.1:5173，/api 与 /ws 代理到 8080）
	cd frontend && $(PNPM) dev

.PHONY: frontend-build
frontend-build:  ## 构建前端产物到 frontend/dist
	cd frontend && $(PNPM) build

.PHONY: frontend-test
frontend-test:  ## 跑前端组件测试（Vitest）
	cd frontend && $(PNPM) test

.PHONY: frontend-check
frontend-check:  ## 构建前端并校验产物预算（CI 同款门禁）
	cd frontend && $(PNPM) build && $(PNPM) check-bundle

.PHONY: frontend-check-all
frontend-check-all:  ## 前端全套门禁：测试 + 构建 + 产物预算
	cd frontend && $(PNPM) test && $(PNPM) build && $(PNPM) check-bundle

.PHONY: frontend-preview
frontend-preview:  ## 本地预览已构建的前端（需后端另跑 ayt-web）
	cd frontend && $(PNPM) preview

.PHONY: web
web:  ## 启动控制台（后端 + 已构建的前端，http://127.0.0.1:8080）
	$(PYTHON) -m src.api.admin --host 127.0.0.1 --port 8080

# ---------- 文档 ----------
.PHONY: docs-install
docs-install:  ## 安装 MkDocs
	$(PIP) install -e ".[docs]"

.PHONY: docs
docs:  ## 本地启动 MkDocs 预览（http://127.0.0.1:8000）
	$(PYTHON) -m mkdocs serve

.PHONY: docs-build
docs-build:  ## 构建 MkDocs 静态站点（site/）
	$(PYTHON) -m mkdocs build --strict

# ---------- Docker ----------
# 先跑上下文预检：docker build 要到很后面才报 "excluded by .dockerignore"，
# 而且一次只报第一个撞上的路径。本仓库吃过两次（!README.md 被 *.md 重新排除、
# 排除了 test/ 但 Dockerfile 有 COPY test/），这个脚本能在不起 Docker 的前提下
# 把 31 条 COPY 源全查一遍。
.PHONY: docker-check
docker-check:  ## 预检 Dockerfile 要的路径有没有被 .dockerignore 排掉
	$(PYTHON) scripts/check_dockerfile_context.py

.PHONY: docker-build
docker-build: docker-check  ## 构建 CPU Docker 镜像（先预检上下文）
	docker build -t $(DOCKER_IMAGE):$(DOCKER_TAG) .

.PHONY: docker-build-gpu
docker-build-gpu: docker-check  ## 构建 GPU (cu128) Docker 镜像（先预检上下文）
	docker build --build-arg TORCH_VARIANT=cu128 -t $(DOCKER_IMAGE):cu128 .

.PHONY: docker-run
docker-run:  ## 启动容器并进 bash
	docker run --rm -it \
	 -p 7860:7860 -p 8000:8000 \
	 -v $(PWD)/dataset:/as/dataset \
	 -v $(PWD)/basemodels:/as/basemodels \
	 -v $(PWD)/runs:/as/runs \
	 -v $(PWD)/logs:/as/logs \
	 $(DOCKER_IMAGE):$(DOCKER_TAG)

.PHONY: docker-gradio
docker-gradio:  ## 启动 Gradio 容器
	docker compose --profile gradio up

.PHONY: docker-serve
docker-serve:  ## 启动 FastAPI 推理服务容器
	docker compose --profile serve up

.PHONY: docker-train
docker-train:  ## 在容器里跑训练（替换 dataset_name 与 epochs）
	@if [ -z "$(DATASET)" ]; then echo "$(RED)错误: 请传 DATASET=name, EPOCHS=100$(RESET)"; exit 1; fi
	docker run --rm \
	 -v $(PWD)/dataset:/as/dataset \
	 -v $(PWD)/basemodels:/as/basemodels \
	 -v $(PWD)/runs:/as/runs \
	 $(DOCKER_IMAGE):$(DOCKER_TAG) \
	 ayt-train $(DATASET) --model yolov8s.pt --epochs $(EPOCHS)

# ---------- Pre-commit ----------
.PHONY: pre-commit-install
pre-commit-install:  ## 安装 git pre-commit hook
	$(PYTHON) -m pre_commit install

.PHONY: pre-commit-run
pre-commit-run:  ## 跑全部 pre-commit hook
	$(PYTHON) -m pre_commit run --all-files

# ---------- 清理 ----------
.PHONY: clean
clean:  ## 清理临时文件（不删 dataset/runs/basemodels/）
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf build/ dist/ frontend/dist/ site/ *.egg-info htmlcov/ .coverage* 2>/dev/null || true
	@echo "$(GREEN)✓ 清理完成（未删 dataset/runs/basemodels/）$(RESET)"

.PHONY: clean-all
clean-all:  ## 深度清理（删 runs/logs/reports/tuning + clean）
	rm -rf runs/ logs/ reports/ tuning/ exports/ model_registry/ Ultralytics/ .ci/ultralytics/ .ci/matplotlib/ 2>/dev/null || true
	$(MAKE) clean
	@echo "$(RED)⚠ 已删所有训练产物 + Ultralytics 缓存$(RESET)"