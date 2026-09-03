"""
集成测试
验证各模块之间的协同工作
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import shutil
import tempfile
import unittest

from src.config_generator import ConfigGenerator, quick_setup
from src.data_validator import Severity, validate_dataset
from src.model_registry import ModelRegistry
from src.notifier import ConsoleNotifier, NotificationLevel, NotificationMessage


class TestIntegration(unittest.TestCase):
    """集成测试：验证模块间协同"""

    @classmethod
    def setUpClass(cls):
        cls.dataset_name = "cabel-damage-mini"
        cls.dataset_path = str(Path("dataset/cabel-damage-mini").resolve())

    def test_validate_then_generate_config(self):
        """测试：先验证数据集，再生成配置"""
        report = validate_dataset(self.dataset_path)
        self.assertTrue(report.is_valid)

        generator = ConfigGenerator()
        config = generator.generate_project_config(self.dataset_name)
        self.assertGreater(config.training_config.epochs, 0)
        self.assertEqual(len(config.dataset_name), len(self.dataset_name))

    def test_full_setup_workflow(self):
        """测试：完整设置工作流"""
        config = quick_setup(self.dataset_name)
        self.assertIsNotNone(config)
        self.assertEqual(config.dataset_name, self.dataset_name)
        self.assertTrue(Path(config.data_yaml_path).exists())

        import yaml
        with open(config.data_yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.assertIn("train", data)
        self.assertIn("val", data)
        self.assertIn("names", data)

    def test_registry_with_notifier(self):
        """测试：注册表与通知器协同"""
        tmpdir = tempfile.mkdtemp()
        try:
            registry = ModelRegistry(base_dir=tmpdir)
            notifier = ConsoleNotifier()

            dummy_model = Path(tmpdir) / "model.pt"
            dummy_model.write_text("dummy")

            version = registry.register(
                model_path=str(dummy_model),
                dataset_name="test-dataset",
                metrics={"mAP50": 0.88},
                tags=["integration-test"],
            )

            msg = NotificationMessage(
                title="Model Registered",
                content=f"Version {version.version_id} registered",
                level=NotificationLevel.SUCCESS,
            )
            result = notifier.send(msg)
            self.assertTrue(result)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_end_to_end_data_pipeline(self):
        """测试：端到端数据处理管道"""
        report = validate_dataset(self.dataset_path)
        self.assertTrue(report.is_valid)
        self.assertIn("total_images", report.stats)
        self.assertGreater(report.stats["total_images"], 0)

        generator = ConfigGenerator()
        dataset_config = generator.generate_data_yaml(self.dataset_name)
        self.assertIsNotNone(dataset_config)
        self.assertTrue(Path(dataset_config).exists())


if __name__ == "__main__":
    unittest.main()
