"""
推理服务单元测试
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
from src.inference_service import InferenceService, DetectionResult, InferenceResponse


class TestInferenceService(unittest.TestCase):
    """测试推理服务模块"""

    @classmethod
    def setUpClass(cls):
        # 自动查找可用的模型文件
        base_dir = Path(__file__).parent.parent
        
        # 优先查找训练结果中的 best.pt
        runs_dir = base_dir / "runs" / "detect"
        cls.model_path = None
        if runs_dir.exists():
            for run_dir in sorted(runs_dir.iterdir(), key=lambda d: d.stat().st_mtime, reverse=True):
                best_pt = run_dir / "weights" / "best.pt"
                if best_pt.exists():
                    cls.model_path = str(best_pt)
                    break
        
        # 如果没有找到训练结果，使用 basemodels 中的预训练模型
        if cls.model_path is None:
            basemodels_dir = base_dir / "basemodels"
            if basemodels_dir.exists():
                for pt_file in sorted(basemodels_dir.glob("*.pt"), key=lambda f: f.stat().st_mtime, reverse=True):
                    cls.model_path = str(pt_file)
                    break
        
        if cls.model_path is None:
            raise unittest.SkipTest("跳过测试: 未找到可用的YOLO模型文件(.pt)")
        
        cls.test_image = "dataset/cabel-damage-mini/images/val/IMG_6278_MOV-5_jpg.rf.ab8fcf694519e850ed70329ec295541e.jpg"
        cls.service = InferenceService(cls.model_path)

    def test_model_loaded(self):
        """测试模型已加载"""
        self.assertIsNotNone(self.service.model)
        self.assertTrue(Path(self.service.model_path).exists())

    def test_class_names(self):
        """测试类别名称"""
        self.assertGreater(len(self.service.class_names), 0)
        self.assertIn(0, self.service.class_names)

    def test_predict_image_path(self):
        """测试图像路径推理"""
        result = self.service.predict(self.test_image, conf=0.25)
        self.assertTrue(result["success"])
        self.assertGreater(result["image_width"], 0)
        self.assertGreater(result["image_height"], 0)
        self.assertIsInstance(result["detections"], list)
        self.assertIn("inference_time", result)

    def test_predict_with_different_conf(self):
        """测试不同置信度阈值"""
        result_low = self.service.predict(self.test_image, conf=0.1)
        result_high = self.service.predict(self.test_image, conf=0.9)
        self.assertTrue(result_low["success"])
        self.assertTrue(result_high["success"])

    def test_predict_batch(self):
        """测试批量推理"""
        images = [
            self.test_image,
            "dataset/cabel-damage-mini/images/val/IMG_6277_MOV-7_jpg.rf.4c84c4fb521c9b0c6f97db3028e26e6f.jpg",
        ]
        results = self.service.predict_batch(images, conf=0.25)
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertTrue(r["success"])

    def test_get_available_models(self):
        """测试获取可用模型"""
        models = self.service.get_available_models()
        self.assertIsInstance(models, list)
        if models:
            self.assertTrue(models[0].exists)
            self.assertGreater(models[0].file_size_mb, 0)

    def test_switch_model(self):
        """测试切换模型"""
        new_path = "runs/detect/cabel-damage-mini_auto/weights/best.pt"
        if Path(new_path).exists():
            success = self.service.switch_model(new_path)
            self.assertTrue(success)
            self.assertEqual(self.service.model_path, new_path)

    def test_switch_nonexistent_model(self):
        """测试切换到不存在的模型"""
        success = self.service.switch_model("nonexistent.pt")
        self.assertFalse(success)


if __name__ == "__main__":
    unittest.main()
