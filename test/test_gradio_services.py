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


class TestExportAndCleanup(unittest.TestCase):
    """训练结束后的导出与回收：不得触碰别的数据集，也不得毁掉可续训的断点。

    回归背景（2026-09-17）：旧实现用 ``dataset_name in item.name`` 子串匹配做
    ``rmtree``，实测 ``dataset="mine"`` 会删掉 ``my-mine-other_auto``（另一个
    数据集的全部产物）；同时把 best.pt 从 run 里 move 走并删掉整个 run 目录，
    导致 last.pt 消失、该 run 不可续训，结果页/下载/按 run 注册随之失效。
    """

    def setUp(self):
        import shutil
        self.shutil = shutil
        self.temp_dir = Path(tempfile.mkdtemp())
        self.service = TrainingService(Path(self.temp_dir), LogService(), use_subprocess=False)
        self.service.exports_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_run(self, name: str, size: int = 32, mtime: float | None = None) -> Path:
        """造一个最小可用的 run 目录（权重 + results.csv）。

        ``mtime`` 显式给定时用于排序断言：同一瞬间创建的目录 mtime 可能并列，
        而「哪个是刚训完的」正是本组测试要区分的。
        """
        import os
        run = self.temp_dir / "runs" / "detect" / name
        (run / "weights").mkdir(parents=True)
        (run / "weights" / "best.pt").write_bytes(b"B" * size)
        (run / "weights" / "last.pt").write_bytes(b"L" * size)
        (run / "results.csv").write_text("epoch,mAP50\n0,0.5\n", encoding="utf-8")
        if mtime is not None:
            os.utime(run, (mtime, mtime))
        return run

    def _point_state_at(self, run: Path) -> None:
        self.service.state.update(best_model_path=str(run / "weights" / "best.pt"))

    def test_cleanup_does_not_touch_other_datasets(self):
        """子串撞车的真实案例：数据集 mine 不能删到 my-mine-other_auto"""
        mine = self._make_run("mine_auto")
        other = self._make_run("my-mine-other_auto")
        self._point_state_at(mine)

        self.service._export_best_model_and_cleanup("mine")

        self.assertTrue(other.is_dir(), "别的数据集的 run 被删了")
        self.assertTrue((other / "weights" / "best.pt").is_file())
        self.assertTrue((other / "results.csv").is_file())

    def test_current_run_stays_complete_and_resumable(self):
        """刚训完的 run 必须原地保留 best.pt 与 last.pt（续训/下载都指着它）"""
        run = self._make_run("mine_auto")
        self._point_state_at(run)

        self.service._export_best_model_and_cleanup("mine")

        self.assertTrue((run / "weights" / "best.pt").is_file(), "best.pt 被 move 走了")
        self.assertTrue((run / "weights" / "last.pt").is_file(), "断点没了，续训无从谈起")
        self.assertTrue((run / "results.csv").is_file())
        self.assertTrue((self.temp_dir / "exports" / "mine.pt").is_file(), "导出件没生成")

    def test_cleanup_never_removes_run_dirs(self):
        """本方法不碰 run 目录：保留策略只留一处（TrainingPipeline._cleanup_old_runs）。

        旧实现在这里自带一套「导出后 rmtree」，与 pipeline 的滚动保留口径不一致，
        正是跨数据集误删的成因。现在它只导出 + 回收旧报告。
        """
        base = 1_700_000_000
        runs = [self._make_run(f"mine_auto{s}", mtime=base + i)
                for i, s in enumerate(["", "-2", "-3"])]
        self._point_state_at(runs[-1])

        self.service._export_best_model_and_cleanup("mine")

        for run in runs:
            self.assertTrue(run.is_dir(), f"{run.name} 被这次清理动过了")
            self.assertTrue((run / "weights" / "best.pt").is_file())
        recycle = self.temp_dir / "runs" / ".recycle"
        self.assertFalse(recycle.exists(), "本方法不应把 run 移入回收站（那是 pipeline 的活）")

    def test_stale_reports_recycled_by_exact_prefix(self):
        """报告清理必须前缀精确匹配：data / _smoke_test 这类短名极易被子串撞车"""
        reports = self.temp_dir / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        mine_old = reports / "pipeline_mine_20260101_000000.json"
        mine_new = reports / "pipeline_mine_20260102_000000.json"
        other = reports / "pipeline_data_20260101_000000.json"
        for item in (mine_old, mine_new, other):
            item.write_text("{}", encoding="utf-8")
        # 让 mine_new 成为「最新」：mtime 决定性排序
        import os
        os.utime(mine_old, (1_700_000_000, 1_700_000_000))
        os.utime(mine_new, (1_800_000_000, 1_800_000_000))

        run = self._make_run("mine_auto")
        self._point_state_at(run)
        self.service._export_best_model_and_cleanup("mine")

        self.assertTrue(other.is_file(), "别的数据集的报告被删/被移走了")
        self.assertTrue(mine_new.is_file(), "本次训练刚写出的报告应留在原位")
        self.assertFalse(mine_old.exists(), "旧的同数据集报告应被移走")
        recycles = list((self.temp_dir / "runs" / ".recycle" / "_reports").glob("pipeline_mine_*"))
        self.assertEqual(len(recycles), 1, recycles)

    def test_current_run_survives_even_if_not_the_newest_by_mtime(self):
        """mtime 并列/倒挂也不影响本次 run 的完整性（本方法不做保留排序）"""
        stale = self._make_run("mine_auto", mtime=1_700_000_000)
        current = self._make_run("mine_auto-2", mtime=1_600_000_000)  # 故意更旧
        self._point_state_at(current)

        self.service._export_best_model_and_cleanup("mine")

        self.assertTrue(current.is_dir(), "本次训练的 run 被动了")
        self.assertTrue((current / "weights" / "last.pt").is_file())
        self.assertTrue(stale.is_dir(), "别的 run 也不该被本方法动")


if __name__ == "__main__":
    unittest.main()
