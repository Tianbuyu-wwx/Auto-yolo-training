# Auto YOLO Training · FastAPI 推理服务

> 完整的 OpenAPI 文档由 FastAPI 自动生成：`/docs`。本文档补充示例与配置。

---

## 启动服务

```bash
# 加载训练好的最佳模型
python serve.py --run runs/detect/my-dataset_auto

# 或显式指定模型
python serve.py --model runs/detect/my-dataset_auto/weights/best.pt

# 自定义主机/端口
python serve.py --model best.pt --host 0.0.0.0 --port 8000
```

---

## 端点清单

| 方法 | 路径 | 说明 |
|---|---|---|
| GET  | `/` | 服务元数据（service / version / model_loaded） |
| GET  | `/health` | 健康检查 |
| GET  | `/models` | 列出可用模型 |
| POST | `/switch_model` | 切换当前模型（运行时热切换） |
| POST | `/predict` | 单图推理（multipart 上传） |
| POST | `/predict_base64` | Base64 图像推理 |
| POST | `/predict_batch` | 批量推理 |
| POST | `/predict_path` | 本地路径推理（白名单目录） |

---

## 端点示例

### POST /predict（multipart）

```bash
curl -X POST http://127.0.0.1:8000/predict \
  -H "X-API-Key: your-secret" \
  -F "file=@test.jpg" \
  -F "conf=0.25" \
  -F "iou=0.45" \
  -F "imgsz=640"
```

**响应**：
```json
{
  "success": true,
  "image_width": 1920,
  "image_height": 1080,
  "detections": [
    {
      "class_id": 0,
      "class_name": "cat",
      "confidence": 0.92,
      "bbox": [100.0, 200.0, 300.0, 400.0]
    }
  ],
  "inference_time": 0.045,
  "model_name": "best.pt",
  "timestamp": "2026-09-03T10:00:00"
}
```

### POST /predict_base64

```bash
curl -X POST http://127.0.0.1:8000/predict_base64 \
  -H "X-API-Key: your-secret" \
  -F "image_base64=$(base64 -w 0 test.jpg)" \
  -F "conf=0.25"
```

### POST /predict_batch

```bash
curl -X POST http://127.0.0.1:8000/predict_batch \
  -H "X-API-Key: your-secret" \
  -F "files=@img1.jpg" \
  -F "files=@img2.jpg" \
  -F "files=@img3.jpg"
```

### POST /predict_path（本地路径）

```bash
curl -X POST http://127.0.0.1:8000/predict_path \
  -H "X-API-Key: your-secret" \
  -F "image_path=dataset/my-dataset/images/val/img001.jpg"
```

---

## 配置

### 环境变量（阶段 B5 引入）

所有变量以 `YOLO_` 为前缀，嵌套字段用 `__`（双下划线）：

```bash
# API Key 认证
export YOLO_API__API_KEY="replace-strong-secret"

# API 服务标题（用于企业定制）
export YOLO_BRAND__API_TITLE="MyFactory Detection API"

# 允许的路径推理目录
export YOLO_API__ALLOWED_IMAGE_DIRS='["dataset","test_images"]'
export YOLO_API__ALLOWED_MODEL_DIRS='["runs","basemodels"]'
```

完整列表见 `.env.example`。

### 命令行参数

```bash
python serve.py --help
```

```
--model MODEL, -m    模型文件路径 (.pt)
--run RUN, -r        训练运行目录（自动查找weights/best.pt）
--host HOST          监听地址（默认 127.0.0.1）
--port PORT, -p      端口（默认 8000）
--api-key KEY        API Key（优先级 > 环境变量）
```

---

## 路径白名单（SSRF / 路径穿越防护）

`POST /predict_path` 只能接受白名单目录下的文件路径。默认白名单：

- 图像：`dataset/`、`test_images/`
- 模型：`runs/`、`basemodels/`

**覆盖白名单**（环境变量）：
```bash
export YOLO_API__ALLOWED_IMAGE_DIRS='["dataset","custom_imgs"]'
export YOLO_API__ALLOWED_MODEL_DIRS='["runs","basemodels","custom_models"]'
```

---

## API Key 认证

### 启用

```bash
export YOLO_API__API_KEY="your-strong-secret"
python serve.py --model best.pt
```

### 调用

所有受保护接口必须带 `X-API-Key` 请求头：

```bash
curl -H "X-API-Key: your-strong-secret" http://127.0.0.1:8000/models
```

### 未启用

`YOLO_API__API_KEY` 为空字符串时，**不启用认证**（任何客户端可调用）。生产部署强烈建议启用。

---

## 安全建议

1. **不要在公网监听**（`--host 0.0.0.0`）+ 不带 API Key
2. **通过反向代理提供 TLS**（Nginx / Caddy）
3. **限制上传大小**：Nginx `client_max_body_size 10M`
4. **限流**：Nginx `limit_req_zone`
5. **监控**：用 `/health` 端点 + Prometheus exporter（阶段 C 计划）

---

## Python 客户端示例

```python
import requests

resp = requests.post(
    "http://127.0.0.1:8000/predict",
    headers={"X-API-Key": "your-secret"},
    files={"file": open("test.jpg", "rb")},
    data={"conf": 0.25, "iou": 0.45, "imgsz": 640},
)
result = resp.json()
for det in result["detections"]:
    print(f"{det['class_name']}: {det['confidence']:.2f} @ {det['bbox']}")
```

异步版：
```python
import httpx

async with httpx.AsyncClient() as client:
    resp = await client.post(
        "http://127.0.0.1:8000/predict",
        headers={"X-API-Key": "your-secret"},
        files={"file": open("test.jpg", "rb")},
        data={"conf": 0.25},
    )
    result = resp.json()
```

---

## 内部实现

服务由 `src.inference_service` 提供，类结构：

```python
class InferenceService:
    """YOLO推理服务"""
    def __init__(self, model_path: str, base_dir: str): ...
    def predict(self, image, conf, iou, imgsz, save) -> dict: ...
    def predict_batch(self, images, conf, iou, imgsz) -> list[dict]: ...
    def get_available_models(self) -> list[ModelInfo]: ...
    def switch_model(self, model_path: str) -> bool: ...
```

FastAPI app 通过 `create_app()` 工厂函数构建。所有 5 个端点用 `Service.model` 的 `_model_lock` 串行化推理调用，避免 GPU 并发问题。

---

## 故障排查

### "Address already in use"
改端口：`--port 8001`

### "Model not loaded"
确认模型文件存在：`ls runs/detect/my-dataset_auto/weights/best.pt`

### "Access denied: path outside allowed directories"
路径不在白名单。检查 `YOLO_API__ALLOWED_IMAGE_DIRS` 环境变量，或用 multipart 上传代替路径推理。

### "401 Invalid API Key"
检查 `X-API-Key` 请求头是否与 `YOLO_API__API_KEY` 完全一致。