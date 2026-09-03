"""
FastAPI 服务 API 测试
使用 TestClient 进行本地测试，无需启动外部服务
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import base64
import io
import unittest
from unittest.mock import MagicMock

from PIL import Image

from src.inference_service import HAS_FASTAPI, InferenceService, create_app

if HAS_FASTAPI:
    from fastapi.testclient import TestClient


class _MockInferenceService(InferenceService):
    """用于测试的 mock 推理服务"""

    def __init__(self, base_dir: str = "."):
        self.base_dir = Path(base_dir)
        self.model_path = "mock_model.pt"
        self.model = MagicMock()  # 标记为已加载
        self.class_names = {0: "damage"}
        self._model_lock = MagicMock()

    def predict(self, image, conf=0.25, iou=0.45, imgsz=640, save=False):
        return {
            "success": True,
            "image_width": 640,
            "image_height": 480,
            "detections": [
                {
                    "class_id": 0,
                    "class_name": "damage",
                    "confidence": 0.95,
                    "bbox": [100.0, 100.0, 200.0, 200.0],
                }
            ],
            "inference_time": 0.05,
            "model_name": "mock_model.pt",
        }

    def predict_batch(self, images, conf=0.25, iou=0.45, imgsz=640):
        return [self.predict(img, conf, iou, imgsz) for img in images]

    def get_available_models(self):
        return []

    def switch_model(self, model_path: str) -> bool:
        return Path(model_path).exists()


def _make_test_image():
    """创建一张测试图像"""
    img = Image.new("RGB", (640, 480), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf


@unittest.skipUnless(HAS_FASTAPI, "FastAPI 未安装")
class TestFastAPIEndpoints(unittest.TestCase):
    """测试 FastAPI 接口"""

    def setUp(self):
        self.service = _MockInferenceService()
        self.app = create_app(service=self.service)
        self.client = TestClient(self.app)

    def test_health_endpoint(self):
        """测试健康检查"""
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "healthy")
        self.assertTrue(data["model_loaded"])

    def test_root_endpoint(self):
        """测试根接口：service 字段来自 branding，不应绑定任何具体业务名"""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # 通用关键词必须存在
        self.assertIn("service", data)
        self.assertIn("YOLO", data["service"])
        # 不应包含任何业务化痕迹
        self.assertNotIn("Cable", data["service"])
        self.assertNotIn("破损", data.get("description", ""))
        # version 必须与 __version__ 一致
        from src.__version__ import __version__
        self.assertEqual(data["version"], __version__)

    def test_models_endpoint(self):
        """测试模型列表"""
        resp = self.client.get("/models")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsInstance(data, list)

    def test_predict_file(self):
        """测试文件上传推理"""
        image_buf = _make_test_image()
        resp = self.client.post(
            "/predict",
            files={"file": ("test.jpg", image_buf, "image/jpeg")},
            data={"conf": 0.25},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("detections", data)
        self.assertEqual(len(data["detections"]), 1)

    def test_predict_base64(self):
        """测试 Base64 推理"""
        image_buf = _make_test_image()
        image_base64 = base64.b64encode(image_buf.read()).decode("utf-8")
        resp = self.client.post(
            "/predict_base64",
            data={"image_base64": image_base64, "conf": 0.25},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])

    def test_predict_batch(self):
        """测试批量推理"""
        image_buf1 = _make_test_image()
        image_buf2 = _make_test_image()
        resp = self.client.post(
            "/predict_batch",
            files=[
                ("files", ("test1.jpg", image_buf1, "image/jpeg")),
                ("files", ("test2.jpg", image_buf2, "image/jpeg")),
            ],
            data={"conf": 0.25},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["total_images"], 2)

    def test_api_key_auth(self):
        """测试 API Key 认证"""
        app = create_app(service=self.service, api_key="secret123")
        client = TestClient(app)

        # 无 Key 应被拒绝
        resp = client.get("/models")
        self.assertEqual(resp.status_code, 401)

        # 带正确 Key 可通过
        resp = client.get("/models", headers={"X-API-Key": "secret123"})
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
