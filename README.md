# Auto YOLO Training

面向 YOLO 目标检测任务的本地自动训练工具。项目将数据集扫描与校验、训练配置生成、模型训练、评估、导出、超参数搜索和推理服务串成一套流程，同时提供命令行、Gradio 界面和 FastAPI 接口。

当前定位是**单机开发与内部验证版本**。它适合在受控环境中建立训练基线，还不是多用户、可恢复的生产训练平台。

## 功能概览

- 扫描 `dataset/` 下的数据集并检查图像、标签、类别和切分情况。
- 自动生成 YOLO `data.yaml` 与训练参数。
- 执行“数据校验 → 训练 → 评估 → 导出 → 通知”的训练流水线。
- 使用 Optuna 搜索模型、图像尺寸、批大小、学习率与优化器。
- 通过 Gradio 管理数据、配置、训练状态和结果。
- 通过 FastAPI 提供单图、Base64、批量和本地受限路径推理。
- 提供模型评估、格式导出和模型注册表等辅助模块。

## 环境要求

- Windows 10/11 或 Linux。当前项目主要在 Windows 上验证。
- Python **3.12.13**（见 `.python-version`）；建议使用该版本建立可复现基线。
- 训练需要足够的磁盘空间与内存。NVIDIA GPU 为可选，但正式训练强烈建议使用兼容的 NVIDIA 驱动、CUDA 与 PyTorch 组合。
- CPU 可以运行数据校验、测试和小规模烟雾训练，但完整训练会很慢。

项目不会提交数据图片、标签、模型权重和训练产物；首次使用前需要自行准备数据集与基础模型。Ultralytics 也可在首次指定标准模型名时下载权重，此操作需要联网。

## 安装

在项目根目录创建独立虚拟环境。PowerShell 示例：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Linux/macOS shell 示例：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

开发和测试依赖单独维护时，再执行：

```bash
python -m pip install -r requirements-dev.txt
```

Windows 可直接使用项目基线脚本安装并验证环境：

```powershell
.\scripts\bootstrap.ps1 -TorchVariant cu128  # RTX/NVIDIA 工作站
.\scripts\verify.ps1
```

无 CUDA 的机器将 `cu128` 改为 `cpu`。本机 CUDA 12.8 的完整传递依赖快照保存在
`requirements-lock-windows-cu128.txt`；CPU CI 使用同一组直接依赖和 CPU Torch wheel。

如果需要特定 CUDA 版本，请先按照 PyTorch 官方安装说明安装匹配的 `torch`，再安装项目依赖。安装完成后可快速确认环境：

```bash
python -c "import torch, ultralytics, gradio, fastapi; print(torch.__version__, torch.cuda.is_available())"
```

## 数据集约定

每个数据集是 `dataset/` 下的一个独立子目录，推荐使用标准 YOLO 检测结构：

```text
dataset/
└── my-dataset/
    ├── data.yaml
    ├── images/
    │   ├── train/
    │   ├── val/
    │   └── test/       # 可选
    └── labels/
        ├── train/
        ├── val/
        └── test/       # 可选
```

图像与标签应同名，例如 `images/train/0001.jpg` 对应 `labels/train/0001.txt`。每行标签采用 YOLO 检测格式：

```text
class_id x_center y_center width height
```

坐标与宽高应归一化到 `0`～`1`。训练流水线会在 `configs/models/` 生成实际使用的配置；其中路径应相对于配置文件自身，而不是绑定某台电脑。例如 `configs/models/data_my-dataset.yaml`：

```yaml
path: ../../dataset/my-dataset
train: images/train
val: images/val
test: images/test
nc: 2
names:
  - class_a
  - class_b
```

数据集目录内的 `data.yaml` 可用于维护 `nc` 和 `names` 等原始元数据。不要在任何配置中保存其他电脑上的绝对路径。将数据投入训练前必须先校验：

```bash
python validate_data.py my-dataset
python validate_data.py my-dataset --json
```

仓库只保留 `dataset/*/data.yaml` 和目录占位文件；图像与标签需通过项目外的数据存储或制品系统分发。

## 命令行使用

以下命令均从项目根目录执行。数据集名称含空格时必须加引号。

### 训练

```bash
python train.py my-dataset
python train.py my-dataset --model yolov8s.pt --imgsz 640 --batch 16 --epochs 150
python train.py my-dataset --override lr0=0.0005 dropout=0.1 device=0
```

只应在数据已经单独通过校验时使用 `--skip-validation`。完整参数可运行 `python train.py --help` 查看。

### 超参数搜索

```bash
python tune.py my-dataset --n-trials 20
python tune.py my-dataset --n-trials 20 --full-pipeline --epochs 150
```

超参数搜索会启动多次训练，耗时和磁盘占用都可能明显增加。

### 评估

```bash
python eval.py runs/detect/my-dataset_auto/weights/best.pt configs/models/data_my-dataset.yaml --dataset my-dataset
python eval.py --run runs/detect/my-dataset_auto --dataset my-dataset
```

### 导出

```bash
python export.py runs/detect/my-dataset_auto/weights/best.pt --formats onnx
python export.py --run runs/detect/my-dataset_auto --formats onnx,engine
python export.py --list
```

TensorRT `engine` 等格式需要额外的系统运行时，且通常与生成它的 GPU/平台相关。

## Gradio 界面

默认仅允许本机访问：

```bash
python gradio_app.py
python gradio_app.py --host 127.0.0.1 --port 7860
```

启动后访问 `http://127.0.0.1:7860`。`--share` 会请求外部分享服务，不应在包含敏感数据的环境中使用。当前界面没有面向公网部署所需的完整认证与权限隔离。

## FastAPI 推理服务

指定模型或训练运行目录启动：

```bash
python serve.py --model runs/detect/my-dataset_auto/weights/best.pt
python serve.py --run runs/detect/my-dataset_auto --host 127.0.0.1 --port 8000
```

建议通过环境变量配置 API Key。PowerShell：

```powershell
$env:YOLO_API_KEY = "replace-with-a-strong-secret"
python serve.py --model runs/detect/my-dataset_auto/weights/best.pt
```

Linux/macOS shell：

```bash
export YOLO_API_KEY="replace-with-a-strong-secret"
python serve.py --model runs/detect/my-dataset_auto/weights/best.pt
```

启动后可访问：

- 健康检查：`http://127.0.0.1:8000/health`
- OpenAPI 文档：`http://127.0.0.1:8000/docs`
- 推理接口：`POST /predict`、`POST /predict_base64`、`POST /predict_batch`
- 模型接口：`GET /models`、`POST /switch_model`

启用认证后，请求受保护接口时需发送 `X-API-Key` 请求头。不要在未配置认证、TLS 和访问控制时监听公网地址。

## 测试与基线检查

运行项目自带测试入口：

```bash
python test/run_tests.py -v
python test/run_tests.py --module test_data_validator -v
```

安装开发依赖后，也可使用 pytest：

```bash
python -m pytest -q
```

提交前至少应完成以下检查：

1. 新建虚拟环境并完成依赖安装。
2. `python validate_data.py <数据集>` 返回成功。
3. 完整测试套件通过。
4. 用少量数据执行 1 个 epoch 的 CPU 或 GPU 烟雾训练。
5. 确认训练后的最佳权重可由 FastAPI 加载，并能完成一次推理。

## 主要目录

```text
src/                 核心训练、校验、评估、导出与服务实现
src/gradio_app/      Gradio 界面、组件和服务层
test/                单元测试与集成测试
dataset/             本地数据集（大文件不纳入 Git）
configs/             自动生成或维护的模型/训练配置
basemodels/          本地基础权重（不纳入 Git）
runs/                Ultralytics 训练运行目录（不纳入 Git）
exports/             模型导出产物（不纳入 Git）
reports/             训练与评估报告（不纳入 Git）
logs/                运行日志（不纳入 Git）
```

## 已知限制

- 训练任务目前运行在 Gradio Web 进程内，尚无独立任务队列、进程隔离、重启恢复与可靠的并发训练能力。
- Gradio 侧尚未形成适用于公网和多用户场景的认证、权限与资源隔离。
- 模型注册表已实现基础模块，但训练产物、配置、数据集版本和模型版本还未完整关联。
- 从旧版本或外部环境导入的 YAML 可能含本机绝对路径；使用前应重新生成或改为相对于 YAML 文件的路径。
- `dataset/data` 当前验证集存在图片与标签不对应的已知问题，不应作为可信训练基线；请优先选择校验通过的数据集。
- PyTorch、CUDA、Ultralytics 和 TensorRT 对版本组合较敏感；更换机器后必须重新执行环境检查和烟雾训练。
- 在受限沙箱中，Polars 可能无法识别虚拟机暴露的 CPU 特性；仅做本地烟雾验证时可临时设置 `POLARS_SKIP_CPU_CHECK=1`，真实部署应先确认 CPU 与 wheel 兼容。
- 输出目录默认在本地磁盘，暂未提供制品归档、磁盘配额和自动清理策略。

## 安全与版本控制

- 不要提交数据集、模型权重、导出模型、运行日志、训练报告、密钥或 `.env` 文件。
- `data.yaml` 只保存类别与相对路径，不应包含凭据或机器专属路径。
- FastAPI 对外提供服务时应配置 API Key，并由反向代理提供 TLS、限流和上传大小限制。
- 第一次提交前可用 `git status --ignored` 检查忽略规则是否符合预期。
