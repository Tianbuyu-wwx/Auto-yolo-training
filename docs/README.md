# Auto YOLO Training

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-181%20passed-brightgreen.svg)](#测试)
[![Ruff](https://img.shields.io/badge/lint-ruff-blue.svg)](https://github.com/astral-sh/ruff)
[![Docker](https://img.shields.io/badge/docker-cpu%20%7C%20cu128-2496ED.svg)](Dockerfile)

通用 YOLO 模型自动训练平台：数据校验、训练、评估、导出、推理一体化。支持 YOLOv5 / YOLOv8 / YOLOv11 / YOLO26 全系列，4 大任务类型（检测 / 分割 / 姿态 / 分类）。

面向需要在受控环境中建立训练基线的开发者与团队。提供命令行、Gradio 界面、FastAPI 推理服务三种入口，并支持 Docker 一键部署。

---

## ✨ 功能特性

| 模块 | 能力 |
|---|---|
| **数据** | 数据集扫描、结构校验、类别一致性检查、分类格式自动转 YOLO |
| **训练** | 5 阶段编排流水线（验证 → 配置 → 调参 → 训练 → 评估 → 导出），自适应超参数 |
| **调参** | Optuna TPE + MedianPruner 搜索（40+ 维度，含数据增强） |
| **评估** | mAP@50 / mAP@50-95 / Precision / Recall / Fitness + 任务感知指标（segment/pose/classify） |
| **导出** | 12 种格式（ONNX / TensorRT / OpenVINO / TorchScript / CoreML / TFLite / 等） |
| **注册表** | ModelRegistry 自动注册训练产物，支持版本对比与提升生产 |
| **模型** | 27 个预训练权重（4 家族 × 5 尺寸 + 4 任务），自动识别 + 一键下载 |
| **接口** | CLI（`ayt-train` / `ayt-serve` 等 7 个）+ Gradio 4 Tab + FastAPI 4 端点 + 通知（钉钉/飞书/企微/Slack） |
| **部署** | Dockerfile（CPU + cu128 双 tag） + docker-compose（4 profile） + Makefile（23 目标） |
| **质量** | pytest 181 passed + ruff 全量规则 + pre-commit 钩子 + MkDocs 文档站 + GitHub Actions CI |

---

## 🚀 快速开始（5 分钟）

### 方式 A：pip 安装（推荐开发）

```bash
# 克隆仓库
git clone https://github.com/Tianbuyu-wwx/Auto-yolo-training.git
cd Auto-yolo-training

# 创建虚拟环境 + 安装依赖
python3.12 -m venv .venv
source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
pip install --upgrade pip

# CPU 版 PyTorch
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

# GPU 版（cu128）
# pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128

# 项目依赖
pip install -e ".[dev]"

# 跑通烟雾测试（验证安装成功）
make smoke
```

### 方式 B：Docker 一键启动

```bash
# CPU 容器
make docker-build
docker run -it --rm -p 7860:7860 -p 8000:8000 \
    -v $(pwd)/dataset:/as/dataset \
    -v $(pwd)/basemodels:/as/basemodels \
    -v $(pwd)/runs:/as/runs \
    ayt:cpu

# 容器内：
ayt-gradio --host 0.0.0.0    # Gradio 界面
ayt-serve  --host 0.0.0.0    # FastAPI 推理服务
ayt-train  my_dataset --model yolov8s.pt --epochs 100   # 训练

# GPU 容器（需 NVIDIA Container Toolkit）
make docker-build-gpu
docker run --gpus all -it --rm -p 7860:7860 -p 8000:8000 \
    -v $(pwd)/dataset:/as/dataset ayt:cu128
```

### 方式 C：docker-compose profile 启动

```bash
docker compose --profile gradio up      # 启动 Gradio 容器
docker compose --profile serve up       # 启动 FastAPI 容器
docker compose --profile cpu up         # 启动 bash 容器
docker compose --profile gpu up         # 启动 GPU bash 容器
```

---

## 📖 文档

完整文档部署在 GitHub Pages：<https://tianbuyu-wwx.github.io/Auto-yolo-training/>

| 文档 | 说明 |
|---|---|
| [快速开始](docs/quickstart.md) | 5 分钟跑通指南 |
| [数据集](docs/datasets.md) | YOLO / 分类 / Roboflow 格式 + 转换 |
| [API 推理服务](docs/api.md) | FastAPI 端点 + 认证 + Python 客户端示例 |
| [第一阶段可信基线](docs/第一阶段可信基线实施记录与后续方案.md) | 项目演进历史 |

---

## 🛠 常用命令（Makefile）

| 命令 | 说明 |
|---|---|
| `make help` | 显示所有目标 |
| `make install` | 安装运行时 + 开发依赖 |
| `make test` | 跑测试套件（181 tests） |
| `make lint` | ruff 检查 |
| `make lint-fix` | ruff 自动修复 |
| `make format` | ruff 自动格式化 |
| `make smoke` | 烟雾训练验证（`_smoke_test` 数据集，CPU 1 epoch） |
| `make smoke-validate` | 烟雾数据校验 |
| `make docs-install` | 安装 MkDocs 依赖 |
| `make docs` | 本地启动 MkDocs 预览（http://127.0.0.1:8000） |
| `make docs-build` | 构建 MkDocs 静态站点（`site/`） |
| `make docker-build` | 构建 CPU Docker 镜像 |
| `make docker-build-gpu` | 构建 GPU（cu128）Docker 镜像 |
| `make docker-gradio` | 启动 Gradio 容器 |
| `make docker-serve` | 启动 FastAPI 推理容器 |
| `make docker-train DATASET=name EPOCHS=100` | 在容器里跑训练 |
| `make pre-commit-install` | 安装 git pre-commit hook |
| `make pre-commit-run` | 跑全部 pre-commit 钩子 |
| `make clean` | 清理 Python 临时文件（保留数据集/产物） |
| `make clean-all` | 深度清理（含 runs/ logs/ Ultralytics 缓存） |

### Python 入口（`pip install` 后 PATH 可用）

```bash
ayt-train     # 训练
ayt-tune      # 超参数搜索
ayt-eval      # 评估
ayt-export    # 导出
ayt-serve     # FastAPI 推理
ayt-validate  # 数据校验
ayt-gradio    # Gradio 界面
ayt-models    # 预训练模型清单与下载（list / local / download）
```

---

## 📊 训练示例

```bash
# 1. 校验数据集
python validate_data.py my-dataset
# 期望输出：验证结果: 通过

# 2. 训练（默认 yolov8s.pt + 150 epochs）
python train.py my-dataset

# 3. 覆盖参数
python train.py my-dataset \
    --model yolo26m.pt \
    --imgsz 1280 \
    --batch 8 \
    --epochs 200 \
    --override lr0=0.0005 dropout=0.1

# 4. 训练后自动评估 + 注册到 ModelRegistry
# （报告输出在 runs/detect/my-dataset_auto/）

# 5. 启动推理服务
python serve.py --run runs/detect/my-dataset_auto
# OpenAPI 文档：http://127.0.0.1:8000/docs
```

### 超参数搜索

```bash
# 20 轮 Optuna 搜索 + 完整流水线训练
python tune.py my-dataset --n-trials 20 --full-pipeline --epochs 150
```

### 模型清单

```bash
# 列出全部 27 个支持的预训练模型
python ayt_models.py list

# 仅列出 detect 任务、yolov8 家族、size=n
python ayt_models.py list --task detect --family yolov8 --size n

# 列出已下载到 basemodels/ 的模型
python ayt_models.py local

# 下载指定模型
python ayt_models.py download yolov8n.pt
```

---

## 🏗 架构

```
┌────────────────────────────────────────────────────────────────────┐
│                       Entry Points（7 CLI + 1 Gradio + 1 API）       │
│  train.py / tune.py / eval.py / export.py / serve.py / validate.py │
│  gradio_app.py / ayt_models.py                                     │
└────────────────────────┬───────────────────────────────────────────┘
                         │
┌────────────────────────┴───────────────────────────────────────────┐
│                     src/training_pipeline.py                         │
│        TrainingPipeline 5 阶段编排（validation → config →          │
│        tuning → training → evaluation → export）                      │
└────────────────────────┬───────────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
   ┌────▼────┐    ┌──────▼──────┐   ┌─────▼──────┐
   │stages  │    │  modules    │   │  services  │
   │(src/   │    │             │   │            │
   │pipeline│    │ data_valid  │   │  grading  │
   │_stages)│    │ config_gen  │   │  app/     │
   │         │    │ evaluator   │   │            │
   │run_val  │    │ hyperparam  │   │  services/ │
   │run_cfg  │    │ model_exp   │   │  train    │
   │run_exp  │    │ model_reg   │   │  data     │
   └────────┘    │ notifier     │   │  log      │
                 │ inference    │   └───────────┘
                 │ settings     │
                 │ model_cat    │   ┌─────────────┐
                 │ task_types   │   │ Ultralytics  │
                 │ task_metrics │──▶│  YOLO 8.4.54 │
                 │ run_artifacts│   │  (v5/v8/v11/ │
                 │ model_dl     │   │   v26/OBB)  │
                 └──────────────┘   └─────────────┘
```

---

## 🌍 支持的模型

| 家族 | 任务 | Size | Ultralytics 模型 |
|---|---|---|---|
| YOLOv5 | detect | n / s / m | `yolov5{n,s,m}.pt` |
| YOLOv8 | detect / segment / pose / classify | n / s / m / l / x | `yolov8{n,s,m,l,x}{,-seg,-pose,-cls}.pt` |
| YOLOv11 | detect | n / s / m / l / x | `yolo11{n,s,m,l,x}.pt` |
| YOLO26 | detect | n / s / m / l / x | `yolo26{n,s,m,l,x}.pt` |

总计 **27 个**预训练权重，详见 [`src/model_catalog.py`](src/model_catalog.py)。

---

## 🧪 测试

```bash
# 跑全部 CPU-safe 测试（181 tests）
make test

# 跑单个文件
python -m pytest test/test_data_validator.py -v

# 跑带 coverage 报告
make test-cov
```

**测试统计**：181 passed, 1 skipped in ~30s（`pytest -m "not gpu and not training"`）。

**测试组织**：

| 文件 | 覆盖 |
|---|---|
| `test_branding.py` | 品牌信息 + env 覆盖 |
| `test_pipeline_stages.py` | 拆分后的阶段函数 |
| `test_task_types.py` | 任务类型枚举 + 模型名构造 |
| `test_task_metrics.py` | 任务感知指标 |
| `test_model_catalog.py` | 模型清单 |
| `test_model_downloader.py` | 模型下载 |
| `test_run_artifacts.py` | 训练产物解析 |
| `test_inference_service.py` | FastAPI 推理 |
| `test_gradio_services.py` | Gradio 服务层 |
| `test_training_pipeline.py` | 训练流水线 |
| `test_fastapi_api.py` | FastAPI 端点 |
| `test_hyperparameter_tuning.py` | Optuna 调参 |
| `test_model_exporter.py` | 模型导出 |
| `test_model_registry.py` | 模型注册表 |
| `test_notifier.py` | 通知 |
| `test_config_generator.py` | 配置生成 |
| `test_dataset_scanner.py` | 数据集扫描 |
| `test_data_validator.py` | 数据校验 |
| `test_evaluator.py` | 评估器 |
| `test_integration.py` | 集成测试 |

---

## 🔧 环境要求

- **Python 3.12.13**（`.python-version` 固定）
- **磁盘**：数据集 + 训练产物视规模而定；建议 50 GB+ 可用空间
- **GPU**（推荐）：NVIDIA + CUDA 12.8，PyTorch 2.11+ 自动检测
- **CPU**：可跑通数据校验、测试、小规模烟雾训练（几秒级）

不提交到 Git 的内容（已在 `.gitignore`）：
- 数据集图片/标签 (`dataset/**/*.{jpg,txt,...}`)
- 模型权重 (`*.pt`, `*.onnx`, `*.engine`)
- 训练产物 (`runs/`, `exports/`, `logs/`, `reports/`, `tuning/`)
- Ultralytics 缓存 (`Ultralytics/`, `model_registry/`)
- 本地分析报告（`full-analysis-*.md`, `generalization-plan-*.md`）

---

## 🔐 安全

- **不要提交**：`*.env`、`*.pem`、`*.key`、API Key、模型权重
- **FastAPI 部署**：必须配置 `YOLO_API__API_KEY`，并由反向代理提供 TLS / 限流
- **Webhook 通知**：内置 SSRF 防护（`WebhookNotifier._is_safe_url`），白名单 `oapi.dingtalk.com` / `open.feishu.cn` / `qyapi.weixin.qq.com` / `hooks.slack.com`
- **pre-commit hook** 自动扫描 `api[_-]?key / secret / token / password` 防止误提交敏感信息

---

## 🤝 贡献

欢迎 Issue / PR。提交前请：

1. `make test` 全部通过
2. `make lint` 无错误
3. `make format` 格式化代码
4. 重要改动写测试

---

## 📝 已知限制与路线图

### 已知限制

- 训练任务目前仍在 Web 进程内（Gradio）执行；无独立任务队列、进程隔离、断点恢复、并发训练
- FastAPI 端点全部同步（Ultralytics `model.predict` 是同步的）
- Gradio 侧尚未形成公网部署的多用户认证 / 权限隔离
- 训练产物 + 数据集版本化未集成（DVC 计划在阶段 C 后）

### 路线图

| 阶段 | 状态 | 内容 |
|---|---|---|
| A 通用化清场 | ✅ | 品牌模块 + 删 P0 + ModelRegistry 接入 + device=auto |
| B 可配置化 | ✅ | pyproject 完整 + ruff 全规则 + Pydantic Settings + 文档 |
| C 通用能力 | ✅ | 4 任务类型 + 27 模型清单 + CLI 下载器 + 任务抽象 |
| D 生产化 | ✅ | Dockerfile + docker-compose + Makefile + pre-commit + MkDocs |
| E CI/CD 多平台 | 计划 | Linux/Mac job + GPU runner + pip-audit + coverage badge |
| F 分布式 | 远期 | 任务队列（Redis/Celery）+ 断点恢复 + 模型注册中心 Web UI |

---

## 📄 许可证

[MIT](LICENSE) © 2026 Auto YOLO Training Contributors

---

## 🔗 相关项目

- [Ultralytics](https://github.com/ultralytics/ultralytics) — 底层 YOLO 框架
- [Optuna](https://github.com/optuna/optuna) — 超参数搜索
- [Gradio](https://github.com/gradio-app/gradio) — Web 界面
- [FastAPI](https://github.com/tiangolo/fastapi) — 推理服务