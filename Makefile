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
#   make docs           - 本地启动 MkDocs 预览
#   make docker-build   - 构建 CPU Docker 镜像
#   make docker-run     - 启动 Gradio 容器

# ---------- 配置 ----------
PYTHON ?= python
PIP ?= pip
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
install install:  ## 安装运行时 + 开发依赖
	$(PIP) install -e ".[dev]"

.PHONY: install-cpu
install-cpu install-cpu:  ## 安装 CPU 版 PyTorch（仅 CPU 机器）
	$(PIP) install --index-url https://download.pytorch.org/whl/cpu torch torchvision
	$(PIP) install -e ".[dev]"

.PHONY: install-gpu
install-gpu install-gpu:  ## 安装 cu128 GPU PyTorch（NVIDIA 机器）
	$(PIP) install --index-url https://download.pytorch.org/whl/cu128 torch torchvision
	$(PIP) install -e ".[dev]"

# ---------- 测试 ----------
.PHONY: test
test test:  ## 跑 CPU-safe 测试套件
	$(PYTHON) -m pytest -m "not gpu and not training" -v --tb=short

.PHONY: test-all
test-all test-all:  ## 跑全部测试（含标记为 gpu/training 的，跳过实际 GPU 训练）
	$(PYTHON) -m pytest -v --tb=short -m "not gpu"

.PHONY: test-cov
test-cov test-cov:  ## 跑测试 + 生成 coverage 报告
	$(PYTHON) -m pytest -m "not gpu and not training" --cov=src --cov-report=html --cov-report=term

# ---------- Lint / 格式 ----------
.PHONY: lint
lint lint:  ## ruff 检查
	$(PYTHON) -m ruff check .

.PHONY: lint-fix
lint-fix lint-fix:  ## ruff 自动修复
	$(PYTHON) -m ruff check --fix .

.PHONY: format
format format:  ## ruff 自动格式化
	$(PYTHON) -m ruff format .

.PHONY: format-check
format-check format-check:  ## 仅检查格式不修改
	$(PYTHON) -m ruff format --check .

.PHONY: typecheck
typecheck typecheck:  ## mypy 静态类型检查（可选，慢）
	$(PYTHON) -m mypy src/

# ---------- 烟雾验证 ----------
.PHONY: smoke
smoke smoke:  ## 跑烟雾训练（_smoke_test 数据集，CPU 1 epoch）
	$(PYTHON) train.py _smoke_test --model yolov8n.pt --imgsz 64 --batch 2 --epochs 1 --skip-validation --override device=

.PHONY: smoke-validate
smoke-validate smoke-validate:  ## 烟雾数据校验
	$(PYTHON) validate_data.py _smoke_test

# ---------- 文档 ----------
.PHONY: docs-install
docs-install docs-install:  ## 安装 MkDocs
	$(PIP) install -e ".[docs]"

.PHONY: docs
docs docs:  ## 本地启动 MkDocs 预览（http://127.0.0.1:8000）
	$(PYTHON) -m mkdocs serve

.PHONY: docs-build
docs-build docs-build:  ## 构建 MkDocs 静态站点（site/）
	$(PYTHON) -m mkdocs build --strict

# ---------- Docker ----------
.PHONY: docker-build
docker-build docker-build:  ## 构建 CPU Docker 镜像
	docker build -t $(DOCKER_IMAGE):$(DOCKER_TAG) .

.PHONY: docker-build-gpu
docker-build-gpu docker-build-gpu:  ## 构建 GPU (cu128) Docker 镜像
	docker build --build-arg TORCH_VARIANT=cu128 -t $(DOCKER_IMAGE):cu128 .

.PHONY: docker-run
docker-run docker-run:  ## 启动容器并进 bash
	docker run --rm -it \
	 -p 7860:7860 -p 8000:8000 \
	 -v $(PWD)/dataset:/as/dataset \
	 -v $(PWD)/basemodels:/as/basemodels \
	 -v $(PWD)/runs:/as/runs \
	 -v $(PWD)/logs:/as/logs \
	 $(DOCKER_IMAGE):$(DOCKER_TAG)

.PHONY: docker-gradio
docker-gradio docker-gradio:  ## 启动 Gradio 容器
	docker compose --profile gradio up

.PHONY: docker-serve
docker-serve docker-serve:  ## 启动 FastAPI 推理服务容器
	docker compose --profile serve up

.PHONY: docker-train
docker-train docker-train:  ## 在容器里跑训练（替换 dataset_name 与 epochs）
	@if [ -z "$(DATASET)" ]; then echo "$(RED)错误: 请传 DATASET=name, EPOCHS=100$(RESET)"; exit 1; fi
	docker run --rm \
	 -v $(PWD)/dataset:/as/dataset \
	 -v $(PWD)/basemodels:/as/basemodels \
	 -v $(PWD)/runs:/as/runs \
	 $(DOCKER_IMAGE):$(DOCKER_TAG) \
	 ayt-train $(DATASET) --model yolov8s.pt --epochs $(EPOCHS)

# ---------- Pre-commit ----------
.PHONY: pre-commit-install
pre-commit-install pre-commit-install:  ## 安装 git pre-commit hook
	$(PYTHON) -m pre_commit install

.PHONY: pre-commit-run
pre-commit-run pre-commit-run:  ## 跑全部 pre-commit hook
	$(PYTHON) -m pre_commit run --all-files

# ---------- 清理 ----------
.PHONY: clean
clean clean:  ## 清理临时文件（不删 dataset/runs/basemodels/）
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf build/ dist/ *.egg-info htmlcov/ .coverage* 2>/dev/null || true
	@echo "$(GREEN)✓ 清理完成（未删 dataset/runs/basemodels/）$(RESET)"

.PHONY: clean-all
clean-all clean-all:  ## 深度清理（删 runs/logs/reports/tuning + clean）
	rm -rf runs/ logs/ reports/ tuning/ exports/ model_registry/ Ultralytics/ .ci/ultralytics/ .ci/matplotlib/ 2>/dev/null || true
	$(MAKE) clean
	@echo "$(RED)⚠ 已删所有训练产物 + Ultralytics 缓存$(RESET)"