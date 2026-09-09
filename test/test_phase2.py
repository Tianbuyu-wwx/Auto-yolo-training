"""
阶段 2（P2）验收测试

覆盖：
1. TrainingConfig.from_ui（参数接线重构）
2. 子进程隔离（worker.py 端到端 + 服务层方法）
3. run / checkpoint 列表
4. 标注可视化预览
5. 断点续训（pipeline resume 分支 + overrides）
6. 结果页辅助（registry markdown、模型清单过滤）
"""

import json
import time
from pathlib import Path
from unittest import mock

import pytest

from src.gradio_app.models.training_state import TrainingConfig


# ----------------------------------------------------------------------
# P2-1 TrainingConfig.from_ui
# ----------------------------------------------------------------------
class TestFromUi:
    def test_full_conversion(self):
        values = {
            "dataset_name": "demo",
            "model": "basemodels/yolov8n.pt",
            "epochs": "80",        # 字符串数字（潜在脏输入）也要能转
            "imgsz": 640,
            "batch": 16,
            "lr0": 0.001,
            "patience": 20,
            "device": "auto (recommended)",  # UI 下拉项 → 空 = 自动
            "cache": "None",                 # UI "None" → None
            "rect": True,
            "workers": 4,
            "unknown_key": "ignored",
        }
        cfg = TrainingConfig.from_ui(values)
        assert cfg.dataset_name == "demo"
        assert cfg.epochs == 80
        assert cfg.device == ""
        assert cfg.cache is None
        assert cfg.model == "basemodels/yolov8n.pt"
        assert cfg.optimizer == "AdamW"  # 缺省键用 dataclass 默认

    def test_device_cpu_passthrough(self):
        cfg = TrainingConfig.from_ui({"device": "cpu"})
        assert cfg.device == "cpu"

    def test_empty_dict_gets_defaults(self):
        cfg = TrainingConfig.from_ui({})
        assert cfg == TrainingConfig()

    def test_to_overrides_includes_resume(self):
        cfg = TrainingConfig(resume_from="runs/detect/x/weights/last.pt")
        assert cfg.to_overrides()["resume"] is True
        assert TrainingConfig().to_overrides()["resume"] is False


# ----------------------------------------------------------------------
# P2-6 子进程隔离
# ----------------------------------------------------------------------
class TestSubprocessIsolation:
    def test_worker_end_to_end_missing_dataset(self, tmp_path):
        """真实子进程：数据集不存在 → worker 写失败状态 → 服务状态回填"""
        from src.gradio_app.services.log_service import LogService
        from src.gradio_app.services.training_service import TrainingService

        svc = TrainingService(tmp_path, LogService(), use_subprocess=True)
        try:
            config = TrainingConfig(dataset_name="no-such-dataset", epochs=1)
            assert svc.start(config) is True
            assert svc.training_proc is not None

            for _ in range(200):  # 最多等 20s（子进程启动 + 流水线快速失败）
                if not svc.state.is_running:
                    break
                time.sleep(0.1)

            assert svc.state.is_running is False
            assert svc.state.success is False
            assert svc.state.error_message  # 有错误信息
            # 日志文件已生成
            log_files = list((tmp_path / "logs").glob("ayt_worker_*.log"))
            assert log_files, "worker 日志文件应存在"
        finally:
            svc.stop()

    def test_stop_touches_flag_file(self, tmp_path):
        from src.gradio_app.services.log_service import LogService
        from src.gradio_app.services.training_service import TrainingService

        svc = TrainingService(tmp_path, LogService(), use_subprocess=True)
        try:
            config = TrainingConfig(dataset_name="no-such-dataset", epochs=1)
            svc.start(config)
            if svc.state.is_running:
                svc.stop()
                assert svc.state.is_stopping
                flag = svc.worker_payload_path.with_suffix(".stop")
                assert flag.exists()
        finally:
            if svc.training_proc and svc.training_proc.poll() is None:
                svc.training_proc.terminate()
            # 等待 waiter 线程收尾，避免 tmp_path 清理竞态
            if svc.training_thread:
                svc.training_thread.join(timeout=15)


# ----------------------------------------------------------------------
# P2-3 run / checkpoint 列表
# ----------------------------------------------------------------------
class TestRunAndCheckpointLists:
    def test_list_runs(self, tmp_path):
        from src.gradio_app.services.log_service import LogService
        from src.gradio_app.services.training_service import TrainingService

        runs = tmp_path / "runs" / "detect"
        (runs / "ds1_auto").mkdir(parents=True)
        (runs / "ds1_auto" / "results.csv").write_text("epoch\n1", encoding="utf-8")
        (runs / "ds2_auto" / "weights").mkdir(parents=True)
        (runs / "ds2_auto" / "weights" / "best.pt").write_bytes(b"w")
        (runs / "empty").mkdir()
        (runs / "results_only_file.txt").write_text("x", encoding="utf-8")

        svc = TrainingService(tmp_path, LogService())
        # sorted(reverse=True)：名称倒序
        assert svc.list_runs() == ["ds2_auto", "ds1_auto"]

    def test_list_checkpoints(self, tmp_path):
        from src.gradio_app.services.log_service import LogService
        from src.gradio_app.services.training_service import TrainingService

        runs = tmp_path / "runs" / "detect"
        (runs / "ds1_auto" / "weights").mkdir(parents=True)
        (runs / "ds1_auto" / "weights" / "last.pt").write_bytes(b"ckpt")
        (runs / "ds2_auto" / "weights").mkdir(parents=True)  # 无 last.pt

        svc = TrainingService(tmp_path, LogService())
        ckpts = svc.list_checkpoints()
        assert len(ckpts) == 1
        assert ckpts[0].endswith("last.pt")


# ----------------------------------------------------------------------
# P2-5 标注可视化预览
# ----------------------------------------------------------------------
class TestAnnotatedPreview:
    def _make_dataset(self, svc, name="pv-ds"):
        """train 集一张 64x64 PNG + 一条 bbox 标签"""
        from PIL import Image

        img_dir = svc.dataset_dir / name / "images" / "train"
        lbl_dir = svc.dataset_dir / name / "labels" / "train"
        img_dir.mkdir(parents=True)
        lbl_dir.mkdir(parents=True)
        img_path = img_dir / "sample.png"
        Image.new("RGB", (64, 64), color=(30, 30, 30)).save(img_path)
        (lbl_dir / "sample.txt").write_text("0 0.5 0.5 0.5 0.5\n", encoding="utf-8")
        # data.yaml 提供类名
        (svc.dataset_dir / name / "data.yaml").write_text(
            "nc: 1\nnames: [cat]\n", encoding="utf-8")
        return img_path

    def test_annotated_samples_generated(self, tmp_path):
        from src.gradio_app.services.dataset_service import DatasetService

        svc = DatasetService(tmp_path)
        self._make_dataset(svc)

        out = svc.get_annotated_samples("pv-ds")
        assert len(out) == 1
        assert Path(out[0]).exists()
        assert Path(out[0]).parent.parent.name == "preview_cache"

    def test_annotated_samples_empty_when_no_images(self, tmp_path):
        from src.gradio_app.services.dataset_service import DatasetService

        svc = DatasetService(tmp_path)
        assert svc.get_annotated_samples("ghost-ds") == []


# ----------------------------------------------------------------------
# P2-4 断点续训
# ----------------------------------------------------------------------
class TestResume:
    def test_run_training_resume_uses_checkpoint_args(self, tmp_path, monkeypatch):
        """cfg.resume=True 时 _run_training 只传 resume 最小参数集"""
        from src.config_generator import ProjectConfig, TrainingConfig as GenTrainingConfig
        from src.training_pipeline import TrainingPipeline

        captured = {}

        class FakeYOLO:
            def __init__(self, path):
                captured["model_path"] = path

            def add_callback(self, *a, **k):
                pass

            def train(self, **kwargs):
                captured["kwargs"] = kwargs

                class R:  # 最小 results 对象
                    results_dict = {"metrics/mAP50(B)": 0.5}

                return R()

        class FakeResults:
            pass

        fake_ultralytics = mock.MagicMock()
        fake_ultralytics.YOLO = FakeYOLO
        monkeypatch.setitem(__import__("sys").modules, "ultralytics", fake_ultralytics)

        ckpt = tmp_path / "last.pt"
        ckpt.write_bytes(b"fake")
        (tmp_path / "runs" / "detect").mkdir(parents=True)  # run 目录扫描需要存在

        gen_cfg = GenTrainingConfig(
            model=str(ckpt), resume=True, device="cpu",
        )
        pc = ProjectConfig(
            project_name="resume_auto",
            dataset_name="resume-ds",
            dataset_path=str(tmp_path),
            output_dir=str(tmp_path / "runs" / "detect" / "resume_auto"),
            data_yaml_path=str(tmp_path / "data.yaml"),
            training_config=gen_cfg,
        )

        pipeline = TrainingPipeline(base_dir=str(tmp_path))
        result = pipeline._run_training(pc)

        assert result.success
        assert captured["kwargs"]["resume"] is True
        # 覆盖参数被剥离（resume 模式以 ckpt 参数为准）
        assert "epochs" not in captured["kwargs"]
        assert "lr0" not in captured["kwargs"]

    def test_no_resume_keeps_full_kwargs(self, tmp_path, monkeypatch):
        from src.config_generator import ProjectConfig, TrainingConfig as GenTrainingConfig
        from src.training_pipeline import TrainingPipeline

        captured = {}

        class FakeYOLO:
            def __init__(self, path):
                pass

            def add_callback(self, *a, **k):
                pass

            def train(self, **kwargs):
                captured.update(kwargs)

                class R:
                    results_dict = {"metrics/mAP50(B)": 0.5}

                return R()

        fake_ultralytics = mock.MagicMock()
        fake_ultralytics.YOLO = FakeYOLO
        monkeypatch.setitem(__import__("sys").modules, "ultralytics", fake_ultralytics)

        model = tmp_path / "basemodels" / "yolov8n.pt"
        model.parent.mkdir(parents=True)
        model.write_bytes(b"fake")
        (tmp_path / "runs" / "detect").mkdir(parents=True)

        gen_cfg = GenTrainingConfig(
            model=str(model), resume=False, device="cpu", epochs=7,
        )
        pc = ProjectConfig(
            project_name="normal_auto",
            dataset_name="normal-ds",
            dataset_path=str(tmp_path),
            output_dir=str(tmp_path / "runs" / "detect" / "normal_auto"),
            data_yaml_path=str(tmp_path / "data.yaml"),
            training_config=gen_cfg,
        )

        pipeline = TrainingPipeline(base_dir=str(tmp_path))
        assert pipeline._run_training(pc).success
        assert captured.get("epochs") == 7
        assert captured.get("resume") is False


# ----------------------------------------------------------------------
# P2-3 结果页辅助
# ----------------------------------------------------------------------
class TestResultViewerHelpers:
    def test_registry_markdown_empty(self, tmp_path):
        from src.gradio_app.components.result_viewer import _registry_markdown
        from src.gradio_app.services.log_service import LogService
        from src.gradio_app.services.training_service import TrainingService

        svc = TrainingService(tmp_path, LogService())
        assert _registry_markdown(svc, None) == "暂无注册版本"
        assert "暂无注册版本" in _registry_markdown(svc, "ds_auto")

    def test_registry_markdown_with_versions(self, tmp_path):
        from src.gradio_app.components.result_viewer import _registry_markdown
        from src.gradio_app.services.log_service import LogService
        from src.gradio_app.services.training_service import TrainingService
        from src.model_registry import ModelRegistry

        svc = TrainingService(tmp_path, LogService())
        model_file = tmp_path / "best.pt"
        model_file.write_bytes(b"fake")

        registry = ModelRegistry(str(tmp_path))
        registry.register(model_path=str(model_file), dataset_name="myds",
                          metrics={"mAP50": 0.83}, copy_model=False)

        md = _registry_markdown(svc, "myds_auto")
        assert "myds" in md
        assert "0.8300" in md


# ----------------------------------------------------------------------
# P2-2 模型清单过滤
# ----------------------------------------------------------------------
class TestModelChoices:
    def test_task_filter_local_first(self, tmp_path, monkeypatch):
        import src.gradio_app.components.config_panel as cp

        # 构造假的 basemodels：本地有 yolov8n-seg.pt
        basemodels = tmp_path / "basemodels"
        basemodels.mkdir()
        (basemodels / "yolov8n-seg.pt").write_bytes(b"fake")
        monkeypatch.setattr(cp, "_basemodels_dir", lambda: basemodels)

        seg_choices = cp._model_choices_for_task("segment")
        values = [v for v, _ in seg_choices]
        labels = [lb for _, lb in seg_choices]

        assert "yolov8n-seg.pt" in values
        # 本地模型标 ✅ 且排最前
        assert labels[0].startswith("✅")
        assert values[0] == "yolov8n-seg.pt"
        # 不含其他任务的模型
        assert "yolov8s-cls.pt" not in values
        # 未下载的清单模型有提示
        missing = [lb for v, lb in seg_choices if v == "yolov8s-seg.pt"]
        assert missing and "未下载" in missing[0]

    def test_default_value_prefers_local(self):
        from src.gradio_app.components.config_panel import _default_model_value

        choices = [("yolov8n-seg.pt", "未下载"), ("yolov8m-seg.pt", "✅ yolov8m-seg.pt")]
        assert _default_model_value(choices) == "yolov8m-seg.pt"
        # 无本地模型时回落到 yolov8s.pt 或首项
        assert _default_model_value([("yolov8n.pt", "x")]) == "yolov8n.pt"
