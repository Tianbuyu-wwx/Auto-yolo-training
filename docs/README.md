<!-- 本文件由 scripts/sync_docs_readme.py 从仓库根 README.md 生成，请勿手改。
     改完根 README 后运行：python scripts/sync_docs_readme.py -->
# Auto YOLO Training

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/Tianbuyu-wwx/Auto-yolo-training/blob/main/LICENSE)
![Tests](https://img.shields.io/badge/tests-371%20passed-brightgreen.svg)
[![Ruff](https://img.shields.io/badge/lint-ruff-blue.svg)](https://github.com/astral-sh/ruff)
[![Docker](https://img.shields.io/badge/docker-cpu%20%7C%20cu128-2496ED.svg)](https://github.com/Tianbuyu-wwx/Auto-yolo-training/blob/main/Dockerfile)

通用 YOLO 模型自动训练平台：数据校验、训练、评估、导出、推理一体化。支持 YOLOv5 / YOLOv8 / YOLOv11 / YOLO26 全系列，4 大任务类型（检测 / 分割 / 姿态 / 分类）。

面向需要在受控环境中建立训练基线的开发者与团队。提供 **Web 控制台**、命令行、FastAPI 推理服务三种入口，并支持 Docker 一键部署。Web 控制台是主界面（Vue 3 SPA，`frontend/`）；原 Gradio 界面已冻结，仅作历史入口保留。

---

## ✨ 功能特性

| 模块 | 能力 |
|---|---|
| **数据** | 数据集扫描、结构校验、类别一致性检查、分类格式自动转 YOLO |
| **训练** | 5 阶段编排流水线（验证 → 配置 → 调参 → 训练 → 评估 → 导出），自适应超参数 |
| **调参** | Optuna TPE + MedianPruner 搜索（40+ 维度，含数据增强） |
| **评估** | mAP@50 / mAP@50-95 / Precision / Recall / Fitness + 任务感知指标（segment/pose/classify） |
| **导出** | 12 种格式（ONNX / TensorRT / OpenVINO / TorchScript / CoreML / TFLite / 等） |
| **注册表** | ModelRegistry 自动注册训练产物；控制台可注册版本、打标、对比、晋升生产、删除 |
| **模型** | 27 个预训练权重（4 家族 × 5 尺寸 + 4 任务），自动识别 + 一键下载 |
| **接口** | **Web 控制台（Vue 3 SPA，7 页）** + CLI（`ayt-web` / `ayt-train` 等 9 个）+ FastAPI 4 端点 + 通知（钉钉/飞书/企微/Slack） |
| **部署** | Dockerfile（CPU + cu128 双 tag，含前端构建阶段） + docker-compose（4 profile） + Makefile（35 目标） |
| **质量** | pytest 371 passed / 1 skipped（Windows + Linux 双平台）+ 覆盖率门禁 ≥69% + ruff 全量规则 + Vitest 组件测试 55 条 + pip-audit 依赖审计 + 打包链路（wheel 内含控制台界面，twine check + 装后自检） + pre-commit 钩子 + MkDocs 文档站 + GitHub Actions CI（含前端构建与产物预算门禁） |

---

## 🚀 快速开始（5 分钟）

### 方式 A：pip 安装（推荐开发）

> 尚未发布到 PyPI（`auto-yolo-training` 名称已确认可用）。发布通路已就绪：
> `make dist` 本地打包 + `.github/workflows/release.yml`（Trusted Publishing），
> 流程见 [打包与发布](publishing.md)。发布后即为 `pip install auto-yolo-training`。

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
docker run -it --rm -p 8080:8080 -p 8000:8000 \
    -v $(pwd)/dataset:/as/dataset \
    -v $(pwd)/basemodels:/as/basemodels \
    -v $(pwd)/runs:/as/runs \
    ayt:cpu

# 容器内：
ayt-web    --host 0.0.0.0 --port 8080   # Web 控制台（Vue SPA + 管理面 API）→ http://localhost:8080
ayt-serve  --host 0.0.0.0               # FastAPI 推理服务
ayt-train  my_dataset --model yolov8s.pt --epochs 100   # 训练

# GPU 容器（需 NVIDIA Container Toolkit）
make docker-build-gpu
docker run --gpus all -it --rm -p 8080:8080 -p 8000:8000 \
    -v $(pwd)/dataset:/as/dataset ayt:cu128
```

> 镜像内已包含构建好的前端产物（构建时由独立的 Node 阶段生成并拷贝到
> `/as/frontend/dist`），`ayt-web` 启动后直接可用，无需在容器里装 Node。

### 方式 C：docker-compose profile 启动

```bash
docker compose --profile gradio up      # 启动 Gradio 容器
docker compose --profile serve up       # 启动 FastAPI 容器
docker compose --profile cpu up         # 启动 bash 容器
docker compose --profile gpu up         # 启动 GPU bash 容器
```

---

## 🖥 Web 控制台

控制台是这套工具的主界面，前端源码在 `frontend/`（Vue 3 + Vite），后端是
`src/api/admin.py` 的管理面 FastAPI。7 个页面：总览 / 数据集 / 训练配置 /
训练监控 / 结果 · 模型库 / 模型注册中心 / 任务队列。

### 生产模式（单进程，同源）

```bash
make frontend-build          # 构建到 frontend/dist
make web                     # 等价于 python -m src.api.admin --host 127.0.0.1 --port 8080
# 打开 http://127.0.0.1:8080
```

后端按 `包内 static/ → 仓库 frontend/dist` 的顺序找界面（源码运行走后者，
`pip` 装出来的 wheel 走前者 —— 打包时已把前端产物装进 `src/api/static/`），
找到后静态托管并启用 SPA 回退；**两处都没有时 `/` 只返回一段 JSON 提示**——
界面空白先查这里。

### 开发模式（热更新）

```bash
make frontend-install        # pnpm install --frozen-lockfile
make frontend-dev            # Vite 起在 5173，/api 与 /ws 代理到 8080
# 另一个终端：
make web                     # 后端 API
# 打开 http://127.0.0.1:5173
```

### 前端测试与产物预算

前端有两道门禁。**组件测试**（Vitest + jsdom）：

```bash
make frontend-test           # 等价于 cd frontend && pnpm test
```

覆盖 REST/WS 封装的边界（错误转文案、WS 自动重连）、组件判定逻辑
（占位态、状态→文案映射）、以及**「后端空数据时 7 个页面都能挂载」的整页冒烟**
—— 后者是前端唯一能自动发现整页白屏的手段。

**产物体积预算**，CI 会跑，本地可单独执行：

```bash
make frontend-check          # 构建 + 校验预算
```

首屏 JS 预算 160 KB、单个 chunk 500 KB。首屏资产由 `dist/index.html` 解析得出，
所以路由懒加载的页面与按需加载的图表库不会被算进首屏。

> **视口要求**：控制台定位为桌面端工具，最低支持 **1024px** 视口宽度。
> 更窄的窗口会显示明确的提示页，而不是让布局静默破版。

### 前端目录结构

```
frontend/
├── index.html
├── vite.config.js          # 开发代理 + 生产分 chunk 策略
├── scripts/check-bundle.mjs# 产物预算门禁
├── test/                   # Vitest 脚手架（假 api 模块 + 空数据契约）
└── src/
    ├── main.js  router.js  App.vue
    ├── lib/                # api.js（REST + WS 封装）、toast.js（全局反馈）
    ├── styles/tokens.css   # 全部设计 token 与组件样式（单一样式来源）
    ├── components/         # LineChart / LogConsole / ToastHost
    └── pages/              # 7 个页面 + NotFoundPage
```

---

## 📖 文档

完整文档部署在 GitHub Pages：<https://tianbuyu-wwx.github.io/Auto-yolo-training/>

| 文档 | 说明 |
|---|---|
| [快速开始](quickstart.md) | 5 分钟跑通指南 |
| [数据集](datasets.md) | YOLO / 分类 / Roboflow 格式 + 转换 |
| [API 推理服务](api.md) | FastAPI 端点 + 路径白名单 + Python 客户端示例 |
| [打包与发布](publishing.md) | 维护者视角：wheel 里的界面、发版流程、Trusted Publishing 配置 |
| [第一阶段可信基线](第一阶段可信基线实施记录与后续方案.md) | 项目演进历史 |

---

## 🛠 常用命令（Makefile）

| 命令 | 说明 |
|---|---|
| `make help` | 显示所有目标 |
| `make install` | 安装运行时 + 开发依赖 |
| `make test` | 跑测试套件（372 tests） |
| `make test-cov-gate` | 覆盖率门禁（CI 同款：地板 69%，基线 73%） |
| `make audit` | 依赖安全审计（pip-audit，本地看全量） |
| `make lint` | ruff 检查 |
| `make lint-fix` | ruff 自动修复 |
| `make format` | ruff 自动格式化 |
| `make smoke` | 烟雾训练验证（`_smoke_test` 数据集，CPU 1 epoch） |
| `make smoke-validate` | 烟雾数据校验 |
| `make gpu-check` | GPU 环境/kernel 检查（秒级，不跑训练） |
| `make gpu-smoke` | GPU 通道验收：标记用例 + 真跑一次 CUDA 训练 |
| `make frontend-install` | 安装前端依赖（pnpm，严格按 lockfile） |
| `make frontend-dev` | 启动前端开发服务器（http://127.0.0.1:5173） |
| `make frontend-build` | 构建前端产物到 `frontend/dist` |
| `make frontend-test` | 跑前端组件测试（Vitest） |
| `make frontend-check` | 构建前端并校验产物预算（CI 同款门禁） |
| `make frontend-check-all` | 前端全套门禁：测试 + 构建 + 产物预算 |
| `make web` | 启动控制台（后端 + 已构建的前端，http://127.0.0.1:8080） |
| `make dist` | 打包 sdist + wheel（含前端产物）并 twine check |
| `make dist-check` | 校验包内静态资源与 `frontend/dist` 是否一致 |
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
ayt-web       # Web 控制台（Vue SPA + 管理面 API，默认 127.0.0.1:8080）
ayt-gradio    # Gradio 界面（已冻结，仅作历史入口）
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
│                 Entry Points（9 CLI，含 ayt-web 控制台）              │
│  train.py / tune.py / eval.py / export.py / serve.py / validate.py │
│  src/api/admin.py（Web 控制台 + 管理面 API） / gradio_app.py（冻结） │
│  ayt_models.py                                                     │
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

总计 **27 个**预训练权重，详见 [`src/model_catalog.py`](https://github.com/Tianbuyu-wwx/Auto-yolo-training/blob/main/src/model_catalog.py)。

---

## 🧪 测试

```bash
# 跑全部 CPU-safe 测试（372 tests）
make test

# 跑单个文件
python -m pytest test/test_data_validator.py -v

# 跑带 coverage 报告
make test-cov
```

**测试统计**：371 passed, 1 skipped in ~20s（`pytest -m "not gpu and not training"`）。

> **GPU 通道**：`gpu` 标记的用例不在上面这条命令里（GitHub 托管的 runner 没有 GPU）。
> 本机验证用 `make gpu-smoke` —— 它先跑标记用例（驱动可见性、算力、**真算一遍 CUDA
> 矩阵乘**并与 CPU 比对），再用 `train.py --device 0` 真跑一次训练，并用 nvidia-smi
> 采样显存/利用率作为「确实在用 GPU」的证据。CI 侧对应 `.github/workflows/gpu.yml`，
> **只能手动触发**且需要自托管 GPU runner（注册步骤见该文件头部注释）。

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
| `test_run_store.py` | run 生命周期（保留 / 回收 / 归档）：精确匹配、可恢复、归档不搬走 run 内权重 |
| `test_gpu_smoke.py` | **GPU 标记**：CUDA kernel 实算校验、Ultralytics 选卡、device 串透传（默认 CI 排除） |
| `test_docs_consistency.py` | 文档一致性守卫：站点首页 == 生成器输出、README 数字 == 套件实测、页面数 == 前端实际 |
| `test_inference_service.py` | FastAPI 推理 |
| `test_admin_api.py` | 管理面 FastAPI（控制台后端）：数据集 / 训练 / 队列 / 导出端点 |
| `test_phase3.py` | 阶段 3：任务队列 / AutoBatch / 多 GPU / 代理调参 / 推理服务 |
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

- **本工具没有账号体系**（有意的）：它面向「下载到自己机器上跑」的个人训练器，不是多人共用的平台，所以控制台与推理服务都不做认证。安全边界就是**监听地址**：两者默认都只绑 `127.0.0.1`
- **要对外提供访问**：不要直接把 `--host` 改成 `0.0.0.0`，请走反向代理（Nginx / Caddy 加 TLS + basic auth）或 VPN/隧道；绑到非回环地址时启动日志会显式警告「任何人都能启停训练、上传数据集、下载权重」
- **不要提交**：`*.env`、`*.pem`、`*.key`、模型权重
- **Webhook 通知**：内置 SSRF 防护（`WebhookNotifier._is_safe_url`），白名单 `oapi.dingtalk.com` / `open.feishu.cn` / `qyapi.weixin.qq.com` / `hooks.slack.com`
- **pre-commit hook** 自动扫描 `api[_-]?key / secret / token / password` 防止误提交敏感信息

---

## 🤝 贡献

欢迎 Issue / PR。提交前请：

1. `make test` 全部通过
2. `make lint` 无错误
3. `make format` 格式化代码
4. 重要改动写测试
5. 改了测试数量或页面数，记得同步本文档里的数字并重跑
   `python scripts/sync_docs_readme.py`（`test/test_docs_consistency.py` 会检查文档是否同步）

---

## 📝 已知限制与路线图

### 已知限制

- **控制台为桌面专用**：最低 1024px 视口，不做移动/平板适配（窄屏显示提示页）
- 控制台**没有认证层**（个人训练器定位，默认只监听 127.0.0.1）；多用户 / 权限隔离**不在路线图上**——需要多人协作请自行加反向代理鉴权
- 数据集状态存在两级口径：`is_ready`（扫描级，labels 目录有标注）与
  `is_trainable`（训练级，存在 `data.yaml`）。两者会不一致——例如有完整标注但
  缺 `data.yaml` 的数据集会显示为「缺 data.yaml」且无法选入训练
- `issues` 告警（如「val 集中 75/75 张图像缺少对应标注」）目前只做展示，
  尚未在提交训练前强制拦截
- FastAPI 端点全部同步（Ultralytics `model.predict` 是同步的）
- 训练产物 + 数据集版本化未集成（DVC 计划在阶段 C 后）

### 路线图

| 阶段 | 状态 | 内容 |
|---|---|---|
| A 通用化清场 | ✅ | 品牌模块 + 删 P0 + ModelRegistry 接入 + device=auto |
| B 可配置化 | ✅ | pyproject 完整 + ruff 全规则 + Pydantic Settings + 文档 |
| C 通用能力 | ✅ | 4 任务类型 + 27 模型清单 + CLI 下载器 + 任务抽象 |
| D 生产化 | ✅ | Dockerfile + docker-compose + Makefile + pre-commit + MkDocs |
| E CI/CD 多平台 | 部分完成 | ✅ Windows+Linux 双平台 job、pip-audit 审计、覆盖率门禁；待做：GPU runner、coverage badge |
| F 分布式 | 远期 | 任务队列（Redis/Celery）—— 其中断点续训与模型注册中心控制台已提前交付（见 G） |
| G 控制台能力补全 | ✅ | 断点续训（从检查点恢复）+ 模型注册中心控制台（注册 / 打标 / 对比 / 晋升 / 删除） |

---

## 📄 许可证

[MIT](https://github.com/Tianbuyu-wwx/Auto-yolo-training/blob/main/LICENSE) © 2026 Auto YOLO Training Contributors

---

## 🔗 相关项目

- [Ultralytics](https://github.com/ultralytics/ultralytics) — 底层 YOLO 框架
- [Optuna](https://github.com/optuna/optuna) — 超参数搜索
- [Gradio](https://github.com/gradio-app/gradio) — Web 界面
- [FastAPI](https://github.com/tiangolo/fastapi) — 推理服务