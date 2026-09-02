"""
FastAPI推理服务
提供模型推理API，支持单图/批量推理
"""

import io
import os
import sys
import json
import base64
import ipaddress
import tempfile
import threading
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Union
from enum import Enum
from urllib.parse import urlparse
import numpy as np
from PIL import Image

from src.utils import is_path_allowed
from src.branding import get_api_metadata, get_brand

try:
    from fastapi import FastAPI, File, UploadFile, Form, HTTPException, BackgroundTasks, Depends, Security
    from fastapi.responses import JSONResponse
    from fastapi.security import APIKeyHeader
    from pydantic import BaseModel, Field
    import uvicorn
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False


class DetectionResult(BaseModel):
    """单目标检测结果"""
    model_config = {"protected_namespaces": ()}

    class_id: int
    class_name: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    bbox: List[float] = Field(..., description="[x1, y1, x2, y2] in pixels")


class InferenceResponse(BaseModel):
    """推理响应"""
    model_config = {"protected_namespaces": ()}

    success: bool
    image_width: int
    image_height: int
    detections: List[DetectionResult]
    inference_time: float
    model_name: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class BatchInferenceResponse(BaseModel):
    """批量推理响应"""
    model_config = {"protected_namespaces": ()}

    success: bool
    results: List[InferenceResponse]
    total_images: int
    total_detections: int
    total_time: float


class ModelInfo(BaseModel):
    """模型信息"""
    model_config = {"protected_namespaces": ()}

    name: str
    path: str
    exists: bool
    file_size_mb: float
    created_at: Optional[str] = None


class InferenceService:
    """YOLO推理服务"""

    # 允许访问的目录白名单
    ALLOWED_IMAGE_DIRS = ["dataset", "test_images"]
    ALLOWED_MODEL_DIRS = ["runs", "basemodels"]

    def __init__(self, model_path: Optional[str] = None, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir) if base_dir else Path(__file__).parent.parent
        self.model_path = model_path
        self.model = None
        self.class_names = {}
        self._model_lock = threading.Lock()

        if model_path and Path(model_path).exists():
            self._load_model(model_path)

    @staticmethod
    def _is_path_allowed(path: str, allowed_dirs: List[str], base_dir: Path) -> bool:
        """检查路径是否在允许的目录范围内（使用统一路径校验工具）"""
        return is_path_allowed(path, allowed_dirs, base_dir)

    def _load_model(self, model_path: str):
        """加载YOLO模型"""
        try:
            from ultralytics import YOLO
            self.model = YOLO(model_path)
            self.model_path = model_path
            self.class_names = self.model.names if hasattr(self.model, 'names') else {}
        except Exception as e:
            raise RuntimeError(f"Failed to load model: {e}")

    def predict(
        self,
        image: Union[str, np.ndarray, Image.Image],
        conf: float = 0.25,
        iou: float = 0.45,
        imgsz: int = 640,
        save: bool = False,
    ) -> Dict[str, Any]:
        """
        对单张图像进行推理

        Args:
            image: 图像路径、numpy数组或PIL图像
            conf: 置信度阈值
            iou: IoU阈值
            imgsz: 输入尺寸
            save: 是否保存结果图

        Returns:
            推理结果字典
        """
        if self.model is None:
            raise RuntimeError("Model not loaded")

        start = datetime.now()

        with self._model_lock:
            results = self.model.predict(
                source=image,
                conf=conf,
                iou=iou,
                imgsz=imgsz,
                save=save,
                verbose=False,
            )

            inference_time = (datetime.now() - start).total_seconds()

            # 解析结果
            detections = []
            result = results[0] if results else None

            if result is not None and result.boxes is not None:
                boxes = result.boxes
                for i in range(len(boxes)):
                    cls_id = int(boxes.cls[i])
                    conf_score = float(boxes.conf[i])
                    xyxy = boxes.xyxy[i].tolist()

                    detections.append({
                        "class_id": cls_id,
                        "class_name": self.class_names.get(cls_id, f"class_{cls_id}"),
                        "confidence": round(conf_score, 4),
                        "bbox": [round(x, 2) for x in xyxy],
                    })

            # 获取图像尺寸
            img_width, img_height = 0, 0
            if result is not None and result.orig_shape is not None:
                img_height, img_width = result.orig_shape[:2]

        return {
            "success": True,
            "image_width": img_width,
            "image_height": img_height,
            "detections": detections,
            "inference_time": round(inference_time, 4),
            "model_name": Path(self.model_path).name if self.model_path else "unknown",
        }

    def predict_batch(
        self,
        images: List[Union[str, np.ndarray, Image.Image]],
        conf: float = 0.25,
        iou: float = 0.45,
        imgsz: int = 640,
    ) -> List[Dict[str, Any]]:
        """
        批量推理

        Args:
            images: 图像列表
            conf: 置信度阈值
            iou: IoU阈值
            imgsz: 输入尺寸

        Returns:
            推理结果列表
        """
        if self.model is None:
            raise RuntimeError("Model not loaded")

        if not images:
            return []

        start = datetime.now()
        with self._model_lock:
            yolo_results = self.model.predict(
                source=images,
                conf=conf,
                iou=iou,
                imgsz=imgsz,
                save=False,
                verbose=False,
            )
            total_time = (datetime.now() - start).total_seconds()

        # 如果只有一张图，predict 返回的是 Results 对象而非列表
        if not isinstance(yolo_results, list):
            yolo_results = [yolo_results]

        per_image_time = total_time / len(images) if images else 0
        results = []
        for result in yolo_results:
            detections = []
            if result.boxes is not None:
                boxes = result.boxes
                for i in range(len(boxes)):
                    cls_id = int(boxes.cls[i])
                    conf_score = float(boxes.conf[i])
                    xyxy = boxes.xyxy[i].tolist()
                    detections.append({
                        "class_id": cls_id,
                        "class_name": self.class_names.get(cls_id, f"class_{cls_id}"),
                        "confidence": round(conf_score, 4),
                        "bbox": [round(x, 2) for x in xyxy],
                    })

            img_width, img_height = 0, 0
            if result.orig_shape is not None:
                img_height, img_width = result.orig_shape[:2]

            results.append({
                "success": True,
                "image_width": img_width,
                "image_height": img_height,
                "detections": detections,
                "inference_time": round(per_image_time, 4),
                "model_name": Path(self.model_path).name if self.model_path else "unknown",
            })

        return results

    def get_available_models(self) -> List[ModelInfo]:
        """获取可用的模型列表"""
        models = []
        runs_dir = self.base_dir / "runs" / "detect"

        if runs_dir.exists():
            for run_dir in runs_dir.iterdir():
                weights_dir = run_dir / "weights"
                if weights_dir.exists():
                    for weight_file in weights_dir.glob("*.pt"):
                        stat = weight_file.stat()
                        models.append(ModelInfo(
                            name=weight_file.stem,
                            path=str(weight_file),
                            exists=True,
                            file_size_mb=round(stat.st_size / (1024 * 1024), 2),
                            created_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        ))

        return sorted(models, key=lambda m: m.created_at or "", reverse=True)

    def switch_model(self, model_path: str) -> bool:
        """切换模型"""
        if not Path(model_path).exists():
            return False
        if not self._is_path_allowed(model_path, self.ALLOWED_MODEL_DIRS, self.base_dir):
            return False
        with self._model_lock:
            self._load_model(model_path)
        return True


# FastAPI应用
def create_app(
    model_path: Optional[str] = None,
    base_dir: Optional[str] = None,
    api_key: Optional[str] = None,
    service: Optional[InferenceService] = None,
) -> FastAPI:
    """创建FastAPI应用"""
    if not HAS_FASTAPI:
        raise ImportError("FastAPI not installed. Run: pip install fastapi uvicorn python-multipart")

    app = FastAPI(**get_api_metadata())

    service = service or InferenceService(model_path, base_dir)

    # API Key认证（可选）
    api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

    async def verify_api_key(key: Optional[str] = Security(api_key_header)):
        """验证API Key（如果配置了的话）"""
        if not api_key:
            return True  # 未配置API Key时不需要认证
        if key != api_key:
            raise HTTPException(status_code=401, detail="Invalid API Key")
        return True

    @app.get("/")
    async def root():
        brand = get_brand()
        return {
            "service": brand["name"],
            "version": brand["version"],
            "tagline": brand["tagline"],
            "model_loaded": service.model is not None,
            "model_path": service.model_path,
        }

    @app.get("/health")
    async def health():
        return {
            "status": "healthy",
            "model_loaded": service.model is not None,
            "timestamp": datetime.now().isoformat(),
        }

    @app.get("/models", response_model=List[ModelInfo])
    async def list_models(authenticated: bool = Depends(verify_api_key)):
        """列出所有可用模型"""
        return service.get_available_models()

    @app.post("/switch_model")
    async def switch_model_endpoint(model_path: str = Form(...), authenticated: bool = Depends(verify_api_key)):
        """切换当前模型"""
        success = service.switch_model(model_path)
        if not success:
            raise HTTPException(status_code=400, detail="Model not found")
        return {"success": True, "model": model_path}

    @app.post("/predict", response_model=InferenceResponse)
    async def predict(
        file: UploadFile = File(...),
        conf: float = Form(0.25),
        iou: float = Form(0.45),
        imgsz: int = Form(640),
        authenticated: bool = Depends(verify_api_key),
    ):
        """单图推理"""
        if service.model is None:
            raise HTTPException(status_code=503, detail="Model not loaded")

        # 读取图像
        contents = await file.read()
        image = Image.open(io.BytesIO(contents))

        # 推理
        result = service.predict(image, conf=conf, iou=iou, imgsz=imgsz)

        return InferenceResponse(**result)

    @app.post("/predict_base64", response_model=InferenceResponse)
    async def predict_base64(
        image_base64: str = Form(...),
        conf: float = Form(0.25),
        iou: float = Form(0.45),
        imgsz: int = Form(640),
        authenticated: bool = Depends(verify_api_key),
    ):
        """Base64图像推理"""
        if service.model is None:
            raise HTTPException(status_code=503, detail="Model not loaded")

        # 解码Base64
        image_data = base64.b64decode(image_base64)
        image = Image.open(io.BytesIO(image_data))

        # 推理
        result = service.predict(image, conf=conf, iou=iou, imgsz=imgsz)

        return InferenceResponse(**result)

    @app.post("/predict_batch", response_model=BatchInferenceResponse)
    async def predict_batch(
        files: List[UploadFile] = File(...),
        conf: float = Form(0.25),
        iou: float = Form(0.45),
        imgsz: int = Form(640),
        authenticated: bool = Depends(verify_api_key),
    ):
        """批量推理"""
        if service.model is None:
            raise HTTPException(status_code=503, detail="Model not loaded")

        start = datetime.now()
        results = []

        for file in files:
            contents = await file.read()
            image = Image.open(io.BytesIO(contents))
            result = service.predict(image, conf=conf, iou=iou, imgsz=imgsz)
            results.append(InferenceResponse(**result))

        total_time = (datetime.now() - start).total_seconds()

        return BatchInferenceResponse(
            success=True,
            results=results,
            total_images=len(results),
            total_detections=sum(len(r.detections) for r in results),
            total_time=round(total_time, 4),
        )

    @app.post("/predict_path")
    async def predict_path(
        image_path: str = Form(...),
        conf: float = Form(0.25),
        iou: float = Form(0.45),
        imgsz: int = Form(640),
        authenticated: bool = Depends(verify_api_key),
    ):
        """本地路径推理"""
        if service.model is None:
            raise HTTPException(status_code=503, detail="Model not loaded")

        if not Path(image_path).exists():
            raise HTTPException(status_code=404, detail="Image not found")

        if not InferenceService._is_path_allowed(image_path, InferenceService.ALLOWED_IMAGE_DIRS, service.base_dir):
            raise HTTPException(status_code=403, detail="Access denied: path outside allowed directories")

        result = service.predict(image_path, conf=conf, iou=iou, imgsz=imgsz)

        return InferenceResponse(**result)

    return app


def run_server(
    model_path: Optional[str] = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    base_dir: Optional[str] = None,
    api_key: Optional[str] = None,
):
    """启动推理服务"""
    if not HAS_FASTAPI:
        print("Error: FastAPI not installed. Run: pip install fastapi uvicorn python-multipart")
        sys.exit(1)

    # 支持环境变量读取 API Key
    effective_api_key = api_key if api_key is not None else os.environ.get("YOLO_API_KEY")
    app = create_app(model_path, base_dir, effective_api_key)

    brand = get_brand()
    print(f"{brand['name']} v{brand['version']} - Inference Server")
    print(f"  Model: {model_path or 'Not specified'}")
    print(f"  Host: {host}")
    print(f"  Port: {port}")
    print(f"  API Docs: http://{host}:{port}/docs")
    print(f"  Health: http://{host}:{port}/health")
    print("-" * 50)

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="YOLO推理服务")
    parser.add_argument("--model", "-m", help="模型路径")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", "-p", type=int, default=8000, help="端口")
    parser.add_argument("--run", "-r", help="训练运行目录（自动查找best.pt）")
    parser.add_argument(
        "--api-key",
        default=os.environ.get("YOLO_API_KEY"),
        help="API认证密钥（默认读取环境变量 YOLO_API_KEY）",
    )

    args = parser.parse_args()

    model_path = args.model
    if args.run:
        run_dir = Path(args.run)
        best_model = run_dir / "weights" / "best.pt"
        if best_model.exists():
            model_path = str(best_model)
        else:
            print(f"Warning: Best model not found in {args.run}")

    run_server(model_path, args.host, args.port, api_key=args.api_key)
