"""
Gradio 应用服务层测试
覆盖 TrainingState、LogService、DatasetService 和 TrainingService 生命周期
"""
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.gradio_app.models.training_state import TrainingConfig, TrainingState
from src.gradio_app.services.dataset_service import DatasetService
from src.gradio_app.services.log_service import LogService
from src.gradio_app.services.training_service import TrainingService


class TestTrainingState(unittest.TestCase):
    """测试训练状态模型"""

    def test_update_and_to_dict(self):
        state = TrainingState()
        state.update(is_running=True, current_epoch=5, total_epochs=10)
        data = state.to_dict()
        self.assertTrue(data["is_running"])
        self.assertEqual(data["current_epoch"], 5)
        self.assertEqual(data["progress"], 50.0)

    def test_progress_when_not_running_success(self):
        state = TrainingState()
        state.update(success=True)
        self.assertEqual(state.to_dict()["progress"], 100.0)

    def test_progress_when_not_running_failed(self):
        state = TrainingState()
        self.assertEqual(state.to_dict()["progress"], 0.0)


class TestLogService(unittest.TestCase):
    """测试日志服务"""

    def test_log_queue_bounded(self):
        """日志队列应有上限，防止 OOM"""
        log_svc = LogService()
        for i in range(LogService.MAX_LOG_LINES + 100):
            log_svc.log_queue.append(f"msg {i}")
        self.assertLessEqual(len(log_svc.log_queue), LogService.MAX_LOG_LINES)

    def test_get_messages_returns_recent(self):
        log_svc = LogService()
        for i in range(10):
            log_svc.log_queue.append(f"msg {i}")
        messages = log_svc.get_messages(max_lines=5)
        self.assertEqual(len(messages.split("\n")), 5)
        self.assertIn("msg 9", messages)


class TestDatasetService(unittest.TestCase):
    """测试数据集服务"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.dataset_dir = Path(self.temp_dir) / "dataset"
        self.dataset_dir.mkdir()

        # 创建一个合法的 YOLO 数据集结构
        for split in ["train", "val"]:
            (self.dataset_dir / "mini-yolo" / "images" / split).mkdir(parents=True)
            (self.dataset_dir / "mini-yolo" / "labels" / split).mkdir(parents=True)

        with open(self.dataset_dir / "mini-yolo" / "data.yaml", "w") as f:
            f.write("train: ../images/train\nval: ../images/val\nnc: 1\nnames: ['damage']\n")

        self.service = DatasetService(Path(self.temp_dir))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_list_datasets_finds_ready_dataset(self):
        datasets = self.service.list_datasets()
        self.assertIn("mini-yolo", datasets)

    def test_get_all_statuses(self):
        statuses = self.service.get_all_statuses()
        self.assertEqual(len(statuses), 1)
        self.assertEqual(statuses[0]["name"], "mini-yolo")


class TestTrainingServiceLifecycle(unittest.TestCase):
    """测试 TrainingService 生命周期（不执行真实训练）"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.log_service = LogService()
        self.service = TrainingService(Path(self.temp_dir), self.log_service)

    def tearDown(self):
        import shutil
        self.service.stop()
        if self.service.training_thread and self.service.training_thread.is_alive():
            self.service.training_thread.join(timeout=2)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cannot_start_twice(self):
        config = TrainingConfig(dataset_name="nonexistent-dataset", epochs=1)
        self.assertTrue(self.service.start(config))
        self.assertFalse(self.service.start(config))
        self.service.stop()

    def test_stop_sets_stopping_state(self):
        config = TrainingConfig(dataset_name="nonexistent-dataset", epochs=1)
        self.service.start(config)
        self.assertTrue(self.service.stop())
        self.assertTrue(self.service.state.is_stopping)

    def test_stop_returns_false_when_not_running(self):
        self.assertFalse(self.service.stop())

    def test_training_fails_gracefully_for_missing_dataset(self):
        config = TrainingConfig(dataset_name="nonexistent-dataset", epochs=1)
        self.service.start(config)
        # 等待工作线程结束（数据集不存在会快速失败）
        for _ in range(50):
            if not self.service.state.is_running:
                break
            time.sleep(0.1)
        self.assertFalse(self.service.state.is_running)
        self.assertFalse(self.service.state.success)
        self.assertIsNotNone(self.service.state.error_message)


if __name__ == "__main__":
    unittest.main()
