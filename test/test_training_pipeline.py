"""
训练流水线核心逻辑测试
使用 mock 替代 Ultralytics YOLO，验证 _run_training 回调与结果解析
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config_generator import ProjectConfig, TrainingConfig
from src.training_pipeline import TrainingPipeline


class TestTrainingPipelineRunTraining(unittest.TestCase):
    """测试训练阶段（_run_training）"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.pipeline = TrainingPipeline(base_dir=self.temp_dir)
        self.project_config = ProjectConfig(
            project_name="test_project",
            dataset_name="test_dataset",
            dataset_path=str(Path(self.temp_dir) / "dataset" / "test_dataset"),
            output_dir=str(Path(self.temp_dir) / "runs" / "detect" / "test_project"),
            data_yaml_path=str(Path(self.temp_dir) / "dataset" / "test_dataset" / "data.yaml"),
            training_config=TrainingConfig(model="yolov8n.pt", epochs=2, imgsz=640, batch=2),
        )

        # 创建输出目录与 data.yaml
        Path(self.project_config.output_dir).mkdir(parents=True, exist_ok=True)
        Path(self.project_config.data_yaml_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.project_config.data_yaml_path).write_text(
            "train: ../images/train\nval: ../images/val\nnc: 1\nnames: ['damage']\n",
            encoding="utf-8",
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("ultralytics.YOLO")
    def test_run_training_success(self, mock_yolo_class):
        """训练成功时应返回正确结果"""
        mock_model = MagicMock()
        mock_results = MagicMock()
        mock_results.results_dict = {"metrics/mAP50(B)": 0.85}
        mock_model.train.return_value = mock_results
        mock_yolo_class.return_value = mock_model

        result = self.pipeline._run_training(self.project_config)

        self.assertTrue(result.success)
        self.assertEqual(result.stage, "training")
        self.assertIn("best_model", result.details)
        mock_model.train.assert_called_once()

    @patch("ultralytics.YOLO")
    def test_run_training_calls_stop_callback(self, mock_yolo_class):
        """注册停止回调后，应在 should_stop 返回 True 时停止训练"""
        mock_model = MagicMock()
        callbacks = {}

        def fake_add_callback(name, fn):
            callbacks[name] = fn

        mock_model.add_callback.side_effect = fake_add_callback
        mock_results = MagicMock()
        mock_results.results_dict = {}
        mock_model.train.return_value = mock_results
        mock_yolo_class.return_value = mock_model

        stop_flag = {"stop": False}

        def should_stop():
            return stop_flag["stop"]

        self.pipeline._run_training(self.project_config, should_stop=should_stop)

        # 验证回调已注册
        self.assertIn("on_epoch_end", callbacks)

        # 模拟训练器对象
        class FakeTrainer:
            def __init__(self):
                self.stop_training = False

        trainer = FakeTrainer()
        callbacks["on_epoch_end"](trainer)
        # 未设置停止标志时，不应触发停止
        self.assertFalse(trainer.stop_training)

        stop_flag["stop"] = True
        callbacks["on_epoch_end"](trainer)
        # 设置停止标志后，应触发停止
        self.assertTrue(trainer.stop_training)

    @patch("ultralytics.YOLO")
    def test_run_training_failure(self, mock_yolo_class):
        """训练异常时应返回失败结果"""
        mock_model = MagicMock()
        mock_model.train.side_effect = RuntimeError("Mock training failure")
        mock_yolo_class.return_value = mock_model

        result = self.pipeline._run_training(self.project_config)

        self.assertFalse(result.success)
        self.assertEqual(result.stage, "training")
        self.assertIn("Mock training failure", result.message)


if __name__ == "__main__":
    unittest.main()
