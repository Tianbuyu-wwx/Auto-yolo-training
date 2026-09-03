"""
阶段 B7 拆分后的 pipeline_stages 单元测试。
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pipeline_stages import run_export, run_validation
from src.training_pipeline import PipelineResult


class TestRunValidation(unittest.TestCase):
    """Stage 1: 数据验证——无状态实现验证"""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_validation_missing_dataset_raises(self):
        """数据集目录不存在时，validate_dataset 内部处理（不算 run_validation 的契约）"""
        # 故意构造：validate_dataset 对不存在的目录会返回带错误的报告
        # 这里仅验证 run_validation 一定返回 PipelineResult
        result = run_validation(self.temp_dir / "nonexistent")
        self.assertIsInstance(result, PipelineResult)
        self.assertEqual(result.stage, "validation")
        # 不存在的目录通常会触发 ERROR 级 issue
        self.assertFalse(result.success)

    def test_validation_smoke_test_dataset_passes(self):
        """_smoke_test 数据集已知通过校验"""
        project_root = Path(__file__).parent.parent
        smoke_path = project_root / "dataset" / "_smoke_test"
        if not smoke_path.exists():
            self.skipTest("_smoke_test 数据集缺失")
        result = run_validation(smoke_path)
        self.assertIsInstance(result, PipelineResult)
        self.assertEqual(result.stage, "validation")
        self.assertTrue(result.success, f"validation 应通过：{result.message}")


class TestRunConfigGeneration(unittest.TestCase):
    """Stage 2: 配置生成——包装 ConfigGenerator"""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.dataset_dir = self.temp_dir / "dataset" / "test_dataset"
        (self.dataset_dir / "images" / "train").mkdir(parents=True)
        (self.dataset_dir / "labels" / "train").mkdir(parents=True)
        # 写一个最小化 data.yaml + 标签
        (self.dataset_dir / "data.yaml").write_text(
            "train: images/train\nval: images/val\nnc: 1\nnames: ['x']\n",
            encoding="utf-8",
        )
        (self.dataset_dir / "labels" / "train" / "a.txt").write_text("0 0.5 0.5 0.2 0.2\n")

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_config_generation_returns_project_config(self):
        """成功时 details 应包含 project_config"""
        from src.pipeline_stages import run_config_generation

        result = run_config_generation(
            dataset_name="test_dataset",
            base_dir=self.temp_dir,
            model="yolov8s.pt",
            imgsz=320,
            batch=2,
            epochs=1,
        )
        self.assertEqual(result.stage, "config_generation")
        self.assertTrue(result.success)
        self.assertIn("project_config", result.details)
        self.assertIn("data_yaml", result.details)
        self.assertIn("config_path", result.details)

    def test_config_generation_failure_for_missing_dataset(self):
        from src.pipeline_stages import run_config_generation

        result = run_config_generation(
            dataset_name="nonexistent",
            base_dir=self.temp_dir,
        )
        self.assertEqual(result.stage, "config_generation")
        self.assertFalse(result.success)


class TestRunExportStage(unittest.TestCase):
    """Stage 5: 模型导出——包装 ModelExporter"""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        # 伪造一个 best.pt（即使不存在也会优雅返回失败）
        self.fake_model = self.temp_dir / "fake_best.pt"
        self.fake_model.write_bytes(b"")

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_export_missing_model_returns_failure(self):
        """模型不存在时应返回 success=False 而非抛异常"""
        result = run_export(
            model_path="/nonexistent/path/model.pt",
            formats=["onnx"],
            imgsz=640,
            base_dir=self.temp_dir,
        )
        self.assertIsInstance(result, PipelineResult)
        self.assertEqual(result.stage, "export")
        self.assertFalse(result.success)

    def test_export_empty_formats_list_accepted(self):
        """空 formats 列表不应崩溃"""
        result = run_export(
            model_path=str(self.fake_model),
            formats=[],
            imgsz=640,
            base_dir=self.temp_dir,
        )
        self.assertIsInstance(result, PipelineResult)


if __name__ == "__main__":
    unittest.main()
