# Auto YOLO Training · Quickstart（5 分钟跑通指南）

> **目标读者：** 新用户。读完本文后你应该能：装环境 → 跑通烟雾训练 → 跑通数据集训练 → 启动 FastAPI 推理服务。

---

## 1. 安装（1 分钟）

### Windows（PowerShell）

```powershell
# 克隆或下载项目
cd E:\项目\auto-yolo-training

# 一键安装（自动建 .venv + 安装 PyTorch + 所有依赖）
.\scripts\bootstrap.ps1 -TorchVariant cu128

# CPU 机器把 cu128 改成 cpu
# 验证环境
.\scripts\verify.ps1
```

### Linux / macOS（bash）

```bash
# CPU
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-dev.txt

# GPU（CUDA 12.8）
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements-dev.txt
```

### 安装验证

```bash
python -c "import torch, ultralytics, gradio, fastapi; print(torch.__version__, torch.cuda.is_available())"
# 期望：2.11.0 True（或 False 但不报错）
```

---

## 2. 烟雾训练（1 分钟）

```bash
python train.py _smoke_test --model yolov8n.pt --imgsz 64 --batch 2 --epochs 1 --skip-validation
```

预期输出：
```
Auto YOLO Training v0.1.0
通用 YOLO 模型自动训练平台 · 数据校验 / 训练 / 评估 / 导出 / 推理
============================================================
数据集: _smoke_test
============================================================
[Stage 3/5] Model training PASSED
[Stage 4/5] Model evaluation PASSED
执行结果: 成功
总耗时: 4.xx 秒
```

`mAP50` 显示为 `0.0000` 是预期的（2 张烟雾图）。

---

## 3. 真实数据集训练（10 分钟）

### 数据集约定

每个数据集是 `dataset/` 下的独立子目录：

```text
dataset/
└── my-dataset/
    ├── data.yaml
    ├── images/
    │   ├── train/    # 训练图
    │   ├── val/      # 验证图
    │   └── test/     # 可选：测试图
    └── labels/
        ├── train/    # 与 train/ 同名（同名 .jpg ↔ .txt）
        ├── val/
        └── test/
```

`data.yaml` 示例：
```yaml
path: ../../dataset/my-dataset
train: images/train
val: images/val
test: images/test       # 可选
nc: 2
names: ['cat', 'dog']
```

### 三步：验证 → 训练 → 评估

```bash
# Step 1：验证数据集
python validate_data.py my-dataset
# 期望：验证结果: 通过

# Step 2：训练
python train.py my-dataset --model yolov8s.pt --imgsz 640 --batch 16 --epochs 150
# 训练产物：runs/detect/my-dataset_auto/weights/best.pt

# Step 3：评估
python eval.py --run runs/detect/my-dataset_auto --dataset my-dataset
```

### 覆盖训练参数

```bash
# 单个参数覆盖
python train.py my-dataset --override lr0=0.0005 dropout=0.1

# 多个参数
python train.py my-dataset --override lr0=0.0005 dropout=0.1 warmup_epochs=5
```

---

## 4. 启动推理服务（1 分钟）

### 方式 A：CLI 启动

```bash
# 加载训练好的最佳模型
python serve.py --run runs/detect/my-dataset_auto

# 或显式指定模型
python serve.py --model runs/detect/my-dataset_auto/weights/best.pt
```

启动后访问：
- 健康检查：`http://127.0.0.1:8000/health`
- OpenAPI 文档：`http://127.0.0.1:8000/docs`
- 推理：`POST /predict`（multipart 上传图）

### 启用 API Key

```powershell
$env:YOLO_API_KEY = "your-strong-secret"
python serve.py --model best.pt
# 请求时需带 header：X-API-Key: your-strong-secret
```

### 方式 B：FastAPI 集成到现有服务

```python
from src.inference_service import create_app

app = create_app(model_path="runs/detect/best.pt", base_dir="/path/to/project")
# 挂载到主 ASGI app
```

---

## 5. 启动 Gradio 界面（1 分钟）

```bash
python gradio_app.py
# 浏览器访问 http://127.0.0.1:7860
```

界面提供 4 个 Tab：
1. **数据集** —— 浏览/上传/校验数据集
2. **配置** —— 选择模型、超参数、3 个预设
3. **训练** —— 启动/停止训练，实时曲线
4. **结果** —— 评估指标、图表、模型路径

---

## 6. 超参数搜索（30 分钟）

```bash
# 搜索 20 轮
python tune.py my-dataset --n-trials 20

# 用最优参数训练
python tune.py my-dataset --n-trials 20 --full-pipeline --epochs 150
```

---

## 7. 常见问题

### 中文乱码
- **Windows：** 显式设置 `PYTHONIOENCODING=utf-8`（已写入 .env.example）
- **Claude/Cursor 等终端：** 自动适配

### 训练卡在 CUDA 'device=0'
- CPU 机器用 `--override device=`（空字符串）或 `--override device=cpu`

### Ultralytics 模型下载失败
- 把 `.pt` 文件手动放到 `basemodels/` 目录

### Polars "sse3" 警告
- 沙箱环境临时绕过：`export POLARS_SKIP_CPU_CHECK=1`

更多问题 → [docs/datasets.md](datasets.md) 和 [docs/api.md](api.md)。

---

## 8. 下一步

- 阅读 [docs/datasets.md](datasets.md) 了解数据集格式与转换
- 阅读 [docs/api.md](api.md) 了解 FastAPI 端点
- 阅读 [docs/第一阶段可信基线实施记录与后续方案.md](第一阶段可信基线实施记录与后续方案.md) 了解项目演进历史