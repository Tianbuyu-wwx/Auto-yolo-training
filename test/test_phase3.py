"""
阶段 3（P3）验收测试

覆盖：
1. AutoBatch / 多 GPU device（from_ui 负数与逗号串、配置面板选项）
2. 代理搜索（proxy_epochs 贯通 tuner objective）
3. test split 评估（evaluator split 参数 + pipeline auto 分支）
4. SQLite 任务队列（TaskQueue 状态机 + QueueRunner 端到端）
5. 训练对比 compare_runs_markdown
6. TensorBoard 检测
7. 异步推理 + 画框端点（predict_annotated + FastAPI 路由注册）
8. Gradio 认证（gradio_auth_credentials 解析）
"""

import io
import time
from pathlib import Path
from unittest import mock

import pytest

from src.gradio_app.models.training_state import TrainingConfig


# ----------------------------------------------------------------------
# P3-1 AutoBatch / 多 GPU
# ----------------------------------------------------------------------
class TestAutoBatchAndMultiGpu:
    def test_from_ui_batch_negative_one(self):
        cfg = TrainingConfig.from_ui({"batch": "-1"})
        assert cfg.batch == -1

    def test_from_ui_device_multi_gpu(self):
        cfg = TrainingConfig.from_ui({"device": "0,1"})
        assert cfg.device == "0,1"

    def test_config_panel_offers_autobatch_and_ddp(self):
        from src.gradio_app.components import config_panel

        source = Path(config_panel.__file__).read_text(encoding="utf-8")
        assert '"-1"' in source and "AutoBatch" in source
        assert '"0,1"' in source and "DDP" in source

    def test_device_value_empty_is_auto(self):
        # device 默认空 = Ultralytics 自动检测；from_ui 对 "" 不做 "auto" 前缀转换
        cfg = TrainingConfig.from_ui({"device": ""})
        assert cfg.device == ""


# ----------------------------------------------------------------------
# P3-1 代理搜索
# ----------------------------------------------------------------------
class TestProxyTuning:
    def test_tuner_uses_proxy_epochs(self, tmp_path):
        from src.hyperparameter_tuning import SearchSpace, YOLOHyperparameterTuner

        tuner = YOLOHyperparameterTuner(
            data_yaml_path=str(tmp_path / "data.yaml"),
            base_dir=str(tmp_path),
            proxy_epochs=7,
        )
        assert tuner.proxy_epochs == 7

    def test_proxy_epochs_in_objective_kwargs(self, tmp_path, monkeypatch):
        """objective 的 train_kwargs 使用 proxy_epochs 作为默认轮数"""
        from src.hyperparameter_tuning import SearchSpace, YOLOHyperparameterTuner

        captured = {}

        class FakeYOLO:
            def __init__(self, path):
                pass

            def train(self, **kwargs):
                captured.update(kwargs)
                return mock.MagicMock(results_dict={"metrics/mAP50(B)": 0.5})

        fake = mock.MagicMock()
        fake.YOLO = FakeYOLO
        monkeypatch.setitem(__import__("sys").modules, "ultralytics", fake)

        tuner = YOLOHyperparameterTuner(
            data_yaml_path=str(tmp_path / "data.yaml"),
            base_dir=str(tmp_path),
            proxy_epochs=13,
        )
        tuner.search_space = SearchSpace()
        tuner.metric = "metrics/mAP50(B)"
        tuner.progress_callback = None

        trial = mock.MagicMock()
        trial.number = 0
        trial.set_user_attr.return_value = None
        trial.report.return_value = None
        trial.should_prune.return_value = False
        trial.study.trials = []
        # _sample_params 返回不含 epochs 的参数 → 走 proxy_epochs 默认
        with mock.patch.object(tuner, "_sample_params", return_value={
            "model": "yolov8s.pt", "imgsz": 640, "batch": 16, "lr0": 0.001,
            "optimizer": "AdamW", "mosaic": 1.0, "mixup": 0.0, "degrees": 0.0,
            "scale": 0.5, "translate": 0.1, "shear": 0.0, "perspective": 0.0,
            "flipud": 0.0, "hsv_h": 0.015, "hsv_s": 0.7, "hsv_v": 0.4,
            "copy_paste": 0.0, "close_mosaic": 10, "dropout": 0.0,
            "label_smoothing": 0.0, "weight_decay": 0.0005, "freeze": 0,
            "box": 7.5, "cls": 0.5, "dfl": 1.5,
        }):
            tuner._objective(trial)

        assert captured["epochs"] == 13

    def test_pipeline_run_accepts_proxy_epochs(self, tmp_path):
        from src.config_generator import ProjectConfig, TrainingConfig as GenTrainingConfig
        from src.training_pipeline import TrainingPipeline

        pipeline = TrainingPipeline(base_dir=str(tmp_path))

        pc = ProjectConfig(
            project_name="whatever_auto", dataset_name="whatever",
            dataset_path=str(tmp_path), output_dir=str(tmp_path / "out"),
            data_yaml_path=str(tmp_path / "data.yaml"),
            training_config=GenTrainingConfig(model="yolov8s.pt"),
        )

        fake_config_result = mock.MagicMock(success=True, stage="stage", message="ok", duration=0.0, error=None, details={
            "data_yaml": str(tmp_path / "data.yaml"), "project_config": pc,
        })
        fake_tune_result = mock.MagicMock(success=True, stage="stage", message="ok", duration=0.0, error=None, details={
            "best_params": {}, "best_value": 0.5, "tuning_result": None,
        })
        fake_train_result = mock.MagicMock(success=True, stage="stage", message="ok", duration=0.0, error=None, details={"metrics": {}, "best_model": None})

        with mock.patch.object(pipeline, "_run_config_generation", return_value=fake_config_result), \
             mock.patch.object(pipeline, "_run_hyperparameter_tuning", return_value=fake_tune_result) as m_tune, \
             mock.patch.object(pipeline, "_run_training", return_value=fake_train_result):
            pipeline.run(
                dataset_name="whatever", enable_tuning=True, tuning_proxy_epochs=11,
                skip_validation=True, enable_evaluation=False,
            )
            m_tune.assert_called_once()
            assert m_tune.call_args.kwargs.get("proxy_epochs") == 11


# ----------------------------------------------------------------------
# P3-1 test split 评估
# ----------------------------------------------------------------------
class TestSplitEvaluation:
    def test_run_evaluation_auto_uses_test_split(self, tmp_path):
        from src.evaluator import EvaluationReport
        from src.training_pipeline import TrainingPipeline

        # 构造 test 目录 → auto 应选择 test
        (tmp_path / "dataset" / "ds" / "images" / "test").mkdir(parents=True)

        pipeline = TrainingPipeline(base_dir=str(tmp_path))

        captured = {}

        def fake_evaluate(**kwargs):
            captured.update(kwargs)
            report = EvaluationReport(model_path="x", dataset_name="ds", data_yaml="y")
            report.metrics.mAP50 = 0.9
            return report

        with mock.patch.object(pipeline.evaluator, "evaluate", side_effect=fake_evaluate):
            pipeline._run_evaluation(
                model_path="x", data_yaml="y", dataset_name="ds", imgsz=640, batch=16,
            )
        assert captured["split"] == "test"

    def test_run_evaluation_auto_falls_back_to_val(self, tmp_path):
        from src.evaluator import EvaluationReport
        from src.training_pipeline import TrainingPipeline

        pipeline = TrainingPipeline(base_dir=str(tmp_path))

        captured = {}

        def fake_evaluate(**kwargs):
            captured.update(kwargs)
            report = EvaluationReport(model_path="x", dataset_name="ds", data_yaml="y")
            report.metrics.mAP50 = 0.9
            return report

        with mock.patch.object(pipeline.evaluator, "evaluate", side_effect=fake_evaluate):
            pipeline._run_evaluation(
                model_path="x", data_yaml="y", dataset_name="no-test-ds", imgsz=640, batch=16,
            )
        assert captured["split"] == "val"

    def test_evaluate_passes_split_to_ultralytics(self, tmp_path, monkeypatch):
        from src.evaluator import ModelEvaluator

        captured = {}

        class FakeYOLO:
            def __init__(self, path):
                pass

            def val(self, **kwargs):
                captured.update(kwargs)
                r = mock.MagicMock()
                r.results_dict = {"metrics/mAP50(B)": 0.5}
                r.orig_shape = (10, 10)
                r.boxes = None
                return r

        fake = mock.MagicMock()
        fake.YOLO = FakeYOLO
        monkeypatch.setitem(__import__("sys").modules, "ultralytics", fake)

        evaluator = ModelEvaluator(str(tmp_path))
        model_file = tmp_path / "x.pt"
        model_file.write_bytes(b"fake")
        evaluator.evaluate(model_path=str(model_file), data_yaml="y.yaml",
                           dataset_name="ds", split="test", save_json=False, save_plots=False)
        assert captured["split"] == "test"

    def test_save_json_disabled_without_pycocotools(self, tmp_path, monkeypatch):
        """回归：pycocotools 缺失时必须禁用 COCO JSON 评估。

        Ultralytics 在 save_json=True 且缺 pycocotools 时会尝试自动 pip 安装，
        离线环境下永久阻塞（冒烟训练卡死 25 分钟的真实事故）。
        """
        from src.evaluator import ModelEvaluator

        captured = {}

        class FakeYOLO:
            def __init__(self, path):
                pass

            def val(self, **kwargs):
                captured.update(kwargs)
                r = mock.MagicMock()
                r.results_dict = {"metrics/mAP50(B)": 0.5}
                r.orig_shape = (10, 10)
                r.boxes = None
                return r

        fake = mock.MagicMock()
        fake.YOLO = FakeYOLO
        monkeypatch.setitem(__import__("sys").modules, "ultralytics", fake)
        # 模拟 pycocotools 缺失
        monkeypatch.setitem(__import__("sys").modules, "pycocotools", None)

        evaluator = ModelEvaluator(str(tmp_path))
        model_file = tmp_path / "x2.pt"
        model_file.write_bytes(b"fake")
        evaluator.evaluate(model_path=str(model_file), data_yaml="y.yaml",
                           dataset_name="ds", save_json=None, save_plots=False)
        assert captured["save_json"] is False

    def test_save_json_forced_true_stays_true(self, tmp_path, monkeypatch):
        from src.evaluator import ModelEvaluator

        captured = {}

        class FakeYOLO:
            def __init__(self, path):
                pass

            def val(self, **kwargs):
                captured.update(kwargs)
                r = mock.MagicMock()
                r.results_dict = {"metrics/mAP50(B)": 0.5}
                r.orig_shape = (10, 10)
                r.boxes = None
                return r

        fake = mock.MagicMock()
        fake.YOLO = FakeYOLO
        monkeypatch.setitem(__import__("sys").modules, "ultralytics", fake)

        evaluator = ModelEvaluator(str(tmp_path))
        model_file = tmp_path / "x3.pt"
        model_file.write_bytes(b"fake")
        evaluator.evaluate(model_path=str(model_file), data_yaml="y.yaml",
                           dataset_name="ds", save_json=True, save_plots=False)
        assert captured["save_json"] is True


# ----------------------------------------------------------------------
# P3-2 SQLite 任务队列
# ----------------------------------------------------------------------
class TestTaskQueue:
    def test_enqueue_and_list(self, tmp_path):
        from src.task_queue import TASK_QUEUED, TaskQueue

        q = TaskQueue(tmp_path / "queue.db")
        tid = q.enqueue("ds1", {"epochs": 5})
        tasks = q.list_tasks()
        assert len(tasks) == 1
        assert tasks[0]["id"] == tid
        assert tasks[0]["status"] == TASK_QUEUED
        assert tasks[0]["config"]["epochs"] == 5

    def test_claim_is_atomic_and_ordered(self, tmp_path):
        from src.task_queue import TASK_RUNNING, TaskQueue

        q = TaskQueue(tmp_path / "queue.db")
        q.enqueue("ds1", {"epochs": 1})
        q.enqueue("ds2", {"epochs": 2})

        first = q.claim_next()
        assert first["dataset_name"] == "ds1"
        assert first["status"] == TASK_RUNNING
        second = q.claim_next()
        assert second["dataset_name"] == "ds2"
        assert q.claim_next() is None

    def test_mark_finished(self, tmp_path):
        from src.task_queue import TaskQueue

        q = TaskQueue(tmp_path / "queue.db")
        tid = q.enqueue("ds", {})
        q.claim_next()
        q.mark_finished(tid, success=False, error="boom")
        task = q.get_task(tid)
        assert task["status"] == "failed"
        assert task["error"] == "boom"

    def test_cancel_queued_and_running(self, tmp_path):
        from src.task_queue import TaskQueue

        q = TaskQueue(tmp_path / "queue.db")
        t1 = q.enqueue("a", {})
        t2 = q.enqueue("b", {})
        q.claim_next()  # t1 → running

        assert q.cancel(t2) is True  # queued → cancelled
        assert q.get_task(t2)["status"] == "cancelled"

        assert q.cancel(t1) is True  # running → cancel_requested
        assert q.is_cancel_requested(t1)
        # 再次 cancel running 任务返回 False（已是 cancel_requested）
        assert q.cancel(t1) is False

    def test_runner_executes_task_end_to_end(self, tmp_path):
        """QueueRunner 通过 worker 子进程执行任务（数据集不存在 → failed）"""
        from src.task_queue import QueueRunner, TaskQueue

        q = TaskQueue(tmp_path / "queue.db")
        q.enqueue("no-such-dataset", TrainingConfig(dataset_name="no-such-dataset", epochs=1).__dict__)
        runner = QueueRunner(q, tmp_path, poll_interval=0.2)
        runner.start()
        try:
            for _ in range(200):  # 最多 20s
                task = q.get_task(1)
                if task["status"] in ("done", "failed", "cancelled"):
                    break
                time.sleep(0.1)
            task = q.get_task(1)
            assert task["status"] == "failed"
            assert task["error"]
        finally:
            runner.stop()

    def test_runner_persists_across_restart(self, tmp_path):
        """队列持久化：新开 TaskQueue 实例能看到旧任务"""
        from src.task_queue import TaskQueue

        TaskQueue(tmp_path / "queue.db").enqueue("ds", {"epochs": 1})
        q2 = TaskQueue(tmp_path / "queue.db")
        assert len(q2.list_tasks()) == 1


# ----------------------------------------------------------------------
# P3-3 训练对比 + TensorBoard
# ----------------------------------------------------------------------
class TestComparisonAndTensorboard:
    def test_compare_runs_markdown(self, tmp_path):
        from src.gradio_app.services.log_service import LogService
        from src.gradio_app.services.training_service import TrainingService

        svc = TrainingService(tmp_path, LogService())
        runs = tmp_path / "runs" / "detect"
        for run in ("a_auto", "b_auto"):
            (runs / run).mkdir(parents=True)
            headers = "epoch,train/box_loss,metrics/mAP50(B),metrics/mAP50-95(B)"
            (runs / run / "results.csv").write_text(
                f"{headers}\n9,0.5,0.{'8' if run.startswith('a') else '6'},0.5\n",
                encoding="utf-8",
            )

        md = svc.compare_runs_markdown(["a_auto", "b_auto"])
        assert "a_auto" in md and "b_auto" in md
        assert "0.8000" in md and "0.6000" in md

    def test_compare_runs_empty(self, tmp_path):
        from src.gradio_app.services.log_service import LogService
        from src.gradio_app.services.training_service import TrainingService

        svc = TrainingService(tmp_path, LogService())
        assert svc.compare_runs_markdown() == "暂无可对比的训练 run"

    def test_tensorboard_detection_returns_bool(self):
        from src.utils import is_tensorboard_available

        assert isinstance(is_tensorboard_available(), bool)


# ----------------------------------------------------------------------
# P3-4 推理：画框方法 + 异步端点
# ----------------------------------------------------------------------
class TestInference:
    def test_predict_annotated_returns_jpeg(self, tmp_path):
        import numpy as np
        from PIL import Image as PILImage

        from src.inference_service import InferenceService

        svc = InferenceService.__new__(InferenceService)
        # 用桩模型替代真实 YOLO（避免下载权重）
        fake_result = mock.MagicMock()
        fake_result.plot.return_value = np.zeros((8, 8, 3), dtype="uint8")
        fake_model = mock.MagicMock()
        fake_model.predict.return_value = [fake_result]
        svc.model = fake_model
        svc._model_lock = __import__("threading").Lock()
        svc.model_path = "fake.pt"

        img = PILImage.new("RGB", (8, 8))
        jpeg = svc.predict_annotated(img)
        assert jpeg[:2] == b"\xff\xd8"  # JPEG magic
        fake_model.predict.assert_called_once()

    def test_predict_image_endpoint_registered(self):
        from fastapi.testclient import TestClient

        from src.inference_service import InferenceService, create_app

        svc = InferenceService.__new__(InferenceService)
        svc.model = None
        svc.model_path = None
        svc.class_names = {}
        svc.base_dir = Path(".")
        svc.allowed_image_dirs = ["dataset"]
        svc.allowed_model_dirs = ["runs", "basemodels"]
        svc._model_lock = __import__("threading").Lock()

        app = create_app(service=svc)
        client = TestClient(app)
        resp = client.post("/predict_image", files={"file": ("a.png", b"fake", "image/png")})
        # 模型未加载 → 503（证明路由存在且走的是业务分支）
        assert resp.status_code == 503


# ----------------------------------------------------------------------
# P3-5 Gradio 认证
# ----------------------------------------------------------------------
class TestGradioAuth:
    def test_parse_credentials(self):
        from src.settings import AySettings, GradioSettings

        s = AySettings(gradio=GradioSettings(auth="admin:s3cret, viewer:pw123"))
        creds = s.gradio_auth_credentials()
        assert creds == [("admin", "s3cret"), ("viewer", "pw123")]

    def test_empty_auth_returns_none(self):
        from src.settings import AySettings

        assert AySettings(gradio__auth="").gradio_auth_credentials() is None

    def test_malformed_pairs_skipped(self):
        from src.settings import AySettings, GradioSettings

        s = AySettings(gradio=GradioSettings(auth="no-colon, admin:pass"))
        assert s.gradio_auth_credentials() == [("admin", "pass")]
