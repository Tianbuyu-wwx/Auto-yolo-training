"""
配置自动生成模块单元测试
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
import tempfile
import yaml
from src.config_generator import (
    ConfigGenerator,
    DatasetConfig,
    TrainingConfig,
    ProjectConfig,
    quick_setup,
)


class TestConfigGenerator(unittest.TestCase):
    """测试配置生成模块"""

    @classmethod
    def setUpClass(cls):
        cls.dataset_name = "cabel-damage-mini"

    def test_dataset_config_to_yaml(self):
        """测试数据集配置转YAML"""
        config = DatasetConfig(
            path="/data/dataset",
            train="images/train",
            val="images/val",
            test="images/test",
            nc=2,
            names=["break", "thunderbolt"],
        )
        yaml_str = config.to_yaml()
        self.assertIn("path: /data/dataset", yaml_str)
        self.assertIn("nc: 2", yaml_str)
        data = yaml.safe_load(yaml_str)
        self.assertEqual(data["nc"], 2)
        self.assertEqual(data["names"], ["break", "thunderbolt"])

    def test_training_config_defaults(self):
        """测试训练配置默认值"""
        config = TrainingConfig()
        self.assertEqual(config.model, "yolov8s.pt")
        self.assertEqual(config.epochs, 150)
        self.assertEqual(config.imgsz, 640)
        self.assertEqual(config.batch, 16)

    def test_quick_setup(self):
        """测试快速设置功能"""
        config = quick_setup(self.dataset_name)
        self.assertIsInstance(config, ProjectConfig)
        self.assertEqual(config.dataset_name, self.dataset_name)
        self.assertIn("data_yaml_path", config.to_dict())

    def test_config_generator_generate_project_config(self):
        """测试生成项目配置"""
        generator = ConfigGenerator()
        config = generator.generate_project_config(self.dataset_name)
        self.assertIsInstance(config, ProjectConfig)
        self.assertEqual(config.dataset_name, self.dataset_name)
        self.assertGreater(config.training_config.epochs, 0)

    def test_project_config_to_dict(self):
        """测试项目配置转字典"""
        training = TrainingConfig(model="yolov8n.pt")
        config = ProjectConfig(
            project_name="test-project",
            dataset_name="test",
            dataset_path="/data",
            output_dir="/output",
            data_yaml_path="data.yaml",
            training_config=training,
        )
        d = config.to_dict()
        self.assertEqual(d["project_name"], "test-project")
        self.assertEqual(d["training_config"]["model"], "yolov8n.pt")

    def test_generate_data_yaml(self):
        """测试生成 data.yaml"""
        generator = ConfigGenerator()
        path = generator.generate_data_yaml(self.dataset_name)
        self.assertTrue(Path(path).exists())
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.assertIn("train", data)
        self.assertIn("val", data)
        self.assertIn("names", data)

    def test_generated_data_yaml_uses_portable_relative_paths(self):
        """data.yaml paths stay valid when the whole project directory moves."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "project"
            dataset_root = project_root / "dataset" / "sample"
            (dataset_root / "images" / "train").mkdir(parents=True)
            (dataset_root / "images" / "val").mkdir(parents=True)

            generator = ConfigGenerator(str(project_root))
            yaml_path = Path(generator.generate_data_yaml("sample", ["part"]))
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))

            self.assertNotIn("path", data)
            self.assertEqual(data["train"], "../../dataset/sample/images/train")
            self.assertEqual(data["val"], "../../dataset/sample/images/val")
            self.assertEqual(
                (yaml_path.parent / data["train"]).resolve(),
                (dataset_root / "images" / "train").resolve(),
            )

    def test_saved_project_config_contains_project_relative_paths(self):
        """Persisted project-owned paths do not contain a machine-specific drive."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "project"
            dataset_root = project_root / "dataset" / "sample"
            (dataset_root / "images" / "train").mkdir(parents=True)
            (dataset_root / "images" / "val").mkdir(parents=True)
            (project_root / "basemodels").mkdir(parents=True)
            (project_root / "basemodels" / "local.pt").touch()

            generator = ConfigGenerator(str(project_root))
            config = generator.generate_project_config(
                "sample", model="local.pt", class_names=["part"]
            )
            saved_path = Path(generator.save_project_config(config))
            saved = yaml.safe_load(saved_path.read_text(encoding="utf-8"))

            self.assertEqual(saved["dataset_path"], "dataset/sample")
            self.assertEqual(saved["output_dir"], "runs/detect/sample_auto")
            self.assertEqual(saved["data_yaml_path"], "configs/models/data_sample.yaml")
            self.assertEqual(saved["training_config"]["model"], "basemodels/local.pt")
            self.assertTrue(all(
                not Path(value).is_absolute()
                for value in (
                    saved["dataset_path"],
                    saved["output_dir"],
                    saved["data_yaml_path"],
                    saved["training_config"]["model"],
                )
            ))

    def test_generate_training_config(self):
        """测试生成训练配置"""
        generator = ConfigGenerator()
        config = generator.generate_training_config(
            dataset_name=self.dataset_name,
            model="yolov8n.pt",
            epochs=10,
        )
        self.assertIsInstance(config, TrainingConfig)
        self.assertEqual(config.model, "yolov8n.pt")
        self.assertEqual(config.epochs, 10)

    def test_discover_datasets(self):
        """测试发现数据集"""
        generator = ConfigGenerator()
        datasets = generator.discover_datasets()
        self.assertIsInstance(datasets, list)
        if datasets:
            self.assertIn(self.dataset_name, datasets)


if __name__ == "__main__":
    unittest.main()
