"""
阶段 1（P1）验收测试

覆盖：
1. device 默认值修复（config_generator 尊重 settings / dataclass 默认空串）
2. 任务感知指标（task_metrics csv 解析 + training_service 状态联动）
3. 数据集上传覆盖保护 + 分类→YOLO 转换服务
4. 训练进度 ETA 估算
5. Gradio 应用可构建（冒烟）
"""

import time
from pathlib import Path
from unittest import mock

import pytest

from src.config_generator import ConfigGenerator
from src.model_catalog import resolve_model_task
from src.task_metrics import (
    infer_task_from_csv_headers,
    primary_loss_from_row,
    primary_metric_labels,
    primary_metrics_from_row,
)


# ----------------------------------------------------------------------
# P1-1 device 默认值
# ----------------------------------------------------------------------
class TestDeviceDefault:
    def test_dataclass_default_is_empty_auto(self):
        from src.config_generator import TrainingConfig

        assert TrainingConfig().device == ""

    def test_generate_training_config_uses_settings_device(self, tmp_path):
        gen = ConfigGenerator(str(tmp_path))

        fake_settings = mock.MagicMock()
        fake_settings.runtime.device = "cpu"
        with mock.patch("src.settings.get_settings", return_value=fake_settings):
            cfg = gen.generate_training_config("any-dataset", epochs=1)

        assert cfg.device == "cpu"

    def test_user_override_beats_settings(self, tmp_path):
        gen = ConfigGenerator(str(tmp_path))

        fake_settings = mock.MagicMock()
        fake_settings.runtime.device = ""
        with mock.patch("src.settings.get_settings", return_value=fake_settings):
            cfg = gen.generate_training_config("any-dataset", epochs=1,
                                               overrides={"device": "0"})

        assert cfg.device == "0"

    def test_train_cli_supports_device_flag(self):
        import subprocess
        import sys

        root = Path(__file__).parent.parent
        result = subprocess.run(
            [sys.executable, str(root / "train.py"), "--help"],
            capture_output=True, text=True, timeout=60,
            # 显式钉住编码：子进程的 stdout 编码取决于环境（PYTHONUTF8 /
            # PYTHONIOENCODING），而父进程 text=True 默认按 locale 解码。两者
            # 不一致时读线程抛 UnicodeDecodeError，stdout 变成 None，断言报的却是
            # TypeError —— 与「CLI 不支持 --device」完全是两回事。
            encoding="utf-8", errors="replace",
        )
        assert result.returncode == 0
        assert "--device" in result.stdout


# ----------------------------------------------------------------------
# P1-2 任务感知指标
# ----------------------------------------------------------------------
class TestTaskMetricsCsv:
    DETECT_HEADERS = ["epoch", "train/box_loss", "metrics/precision(B)",
                      "metrics/recall(B)", "metrics/mAP50(B)", "metrics/mAP50-95(B)"]
    SEGMENT_HEADERS = ["epoch", "train/box_loss", "metrics/mAP50(M)", "metrics/mAP50-95(M)"]
    CLASSIFY_HEADERS = ["epoch", "train/loss", "metrics/accuracy_top1", "metrics/accuracy_top5"]

    def test_infer_task_from_headers(self):
        assert infer_task_from_csv_headers(self.DETECT_HEADERS).value == "detect"
        assert infer_task_from_csv_headers(self.SEGMENT_HEADERS).value == "segment"
        assert infer_task_from_csv_headers(self.CLASSIFY_HEADERS).value == "classify"

    def test_primary_metrics_detect_row(self):
        row = dict(zip(self.DETECT_HEADERS, ["10", "1.5", "0.8", "0.7", "0.9", "0.6"], strict=True))
        out = primary_metrics_from_row(row, "detect")
        assert out == {"mAP@50": 0.9, "mAP@50-95": 0.6}

    def test_primary_metrics_segment_row(self):
        row = dict(zip(self.SEGMENT_HEADERS, ["10", "1.5", "0.88", "0.55"], strict=True))
        out = primary_metrics_from_row(row, "segment")
        assert out == {"mAP@50 (Mask)": 0.88, "mAP@50-95 (Mask)": 0.55}

    def test_primary_metrics_classify_row(self):
        row = dict(zip(self.CLASSIFY_HEADERS, ["10", "2.1", "0.95", "0.99"], strict=True))
        out = primary_metrics_from_row(row, "classify")
        assert out == {"Accuracy@1": 0.95, "Accuracy@5": 0.99}

    def test_primary_metrics_fallback_when_task_keys_missing(self):
        # 任务判定为 segment 但行里只有 detect 列 → 回退扫描任意 mAP50 列
        row = dict(zip(self.DETECT_HEADERS, ["10", "1.5", "0.8", "0.7", "0.9", "0.6"], strict=True))
        out = primary_metrics_from_row(row, "segment")
        assert out == {"mAP@50": 0.9}

    def test_primary_loss(self):
        detect_row = dict(zip(self.DETECT_HEADERS, ["10", "1.5", "0", "0", "0", "0"], strict=True))
        classify_row = dict(zip(self.CLASSIFY_HEADERS, ["10", "2.1", "0", "0"], strict=True))
        assert primary_loss_from_row(detect_row) == 1.5
        assert primary_loss_from_row(classify_row) == 2.1

    def test_primary_metric_labels(self):
        assert primary_metric_labels("detect") == ("mAP@50", "mAP@50-95")
        assert primary_metric_labels("classify") == ("Accuracy@1", "Accuracy@5")

    def test_extract_task_metrics_accepts_plain_dict(self):
        from src.task_metrics import extract_task_metrics

        out = extract_task_metrics({"metrics/mAP50(M)": 0.7, "metrics/mAP50-95(M)": 0.4}, "segment")
        assert out == {"mAP@50 (Mask)": 0.7, "mAP@50-95 (Mask)": 0.4}

    def test_resolve_model_task(self):
        assert resolve_model_task("yolov8s.pt") == "detect"
        assert resolve_model_task("yolov8n-seg.pt") == "segment"
        assert resolve_model_task("yolov8s-pose.pt") == "pose"
        assert resolve_model_task("yolov8n-cls.pt") == "classify"
        assert resolve_model_task("custom_model.pt") == "detect"


class TestTrainingServiceTaskAware:
    """training_service 的任务感知与 ETA（P1-2 / P1-4）"""

    @pytest.fixture()
    def svc(self, tmp_path):
        from src.gradio_app.services.log_service import (
            LogService,
            LogService as _LS,  # noqa: F401
        )
        from src.gradio_app.services.training_service import TrainingService

        svc = TrainingService(tmp_path, LogService())
        yield svc
        svc.stop()

    @pytest.mark.parametrize("model,task", [
        ("yolov8s.pt", "detect"),
        ("yolov8n-seg.pt", "segment"),
        ("yolov8n-cls.pt", "classify"),
    ])
    def test_start_sets_task_and_labels(self, svc, model, task):
        from src.gradio_app.models.training_state import TrainingConfig

        config = TrainingConfig(dataset_name="no-such-dataset", model=model, epochs=1)
        assert svc.start(config) is True
        assert svc.state.task == task
        if task == "classify":
            assert svc.state.metric_labels == ("Accuracy@1", "Accuracy@5")
        elif task == "segment":
            assert svc.state.metric_labels == ("mAP@50 (Mask)", "mAP@50-95 (Mask)")
        else:
            assert svc.state.metric_labels == ("mAP@50", "mAP@50-95")
        svc.stop()
        for _ in range(50):
            if not svc.state.is_running:
                break
            time.sleep(0.1)

    def _write_results_csv(self, runs_dir: Path, headers: list[str], row: list[str]):
        run = runs_dir / "demo_auto"
        run.mkdir(parents=True, exist_ok=True)
        csv = run / "results.csv"
        csv.write_text(",".join(headers) + "\n" + ",".join(row), encoding="utf-8")

    def test_update_from_results_segment_columns(self, svc, tmp_path):
        headers = ["epoch", "train/box_loss", "metrics/mAP50(M)", "metrics/mAP50-95(M)"]
        self._write_results_csv(tmp_path / "runs" / "detect", headers,
                                ["5", "1.25", "0.77", "0.44"])
        svc.state.update(is_running=True, total_epochs=100, task="segment")
        svc._update_from_results()

        assert svc.state.current_epoch == 6
        assert svc.state.current_map50 == pytest.approx(0.77)
        assert svc.state.current_map50_95 == pytest.approx(0.44)
        assert svc.state.current_loss == pytest.approx(1.25)
        assert svc.state.loss_history[-1] == {"epoch": 6, "loss": 1.25}
        assert svc.state.map_history[-1] == {"epoch": 6, "mAP": 0.77}

    def test_update_from_results_classify_columns(self, svc, tmp_path):
        headers = ["epoch", "train/loss", "metrics/accuracy_top1", "metrics/accuracy_top5"]
        self._write_results_csv(tmp_path / "runs" / "detect", headers,
                                ["3", "0.9", "0.91", "0.99"])
        svc.state.update(is_running=True, total_epochs=50, task="classify")
        svc._update_from_results()

        assert svc.state.current_map50 == pytest.approx(0.91)
        assert svc.state.current_map50_95 == pytest.approx(0.99)
        assert svc.state.current_loss == pytest.approx(0.9)

    def test_get_training_results_reports_task_labels(self, svc, tmp_path):
        (tmp_path / "runs" / "detect" / "demo_auto").mkdir(parents=True)
        headers = ["epoch", "train/loss", "metrics/accuracy_top1", "metrics/accuracy_top5"]
        self._write_results_csv(tmp_path / "runs" / "detect", headers, ["9", "0.4", "0.93", "0.98"])

        results = svc.get_training_results()
        assert results["task"] == "classify"
        assert results["metric_labels"] == ("Accuracy@1", "Accuracy@5")
        assert results["final_metrics"]["primary"] == {"Accuracy@1": 0.93, "Accuracy@5": 0.98}
        assert results["final_metrics"]["mAP50"] == 0.93

    def test_eta_estimation_grows_samples(self, svc):
        svc.state.update(total_epochs=10, current_epoch=2)
        base = time.time() - 30
        assert svc._estimate_eta(base) is None  # 样本不足
        svc._estimate_eta(base + 10)
        svc._estimate_eta(base + 20)
        eta = svc._estimate_eta(base + 30)
        assert eta is not None
        assert 0 < eta <= 8 * 10  # 平均 10s/epoch × 剩余 8 个 epoch（含波动余量）

    def test_eta_zero_when_all_epochs_done(self, svc):
        svc.state.update(total_epochs=10, current_epoch=10)
        assert svc._estimate_eta(time.time()) == 0.0


# ----------------------------------------------------------------------
# P1-6 上传覆盖保护 + 转换服务
# ----------------------------------------------------------------------
class TestDatasetUploadProtection:
    @pytest.fixture()
    def svc(self, tmp_path):
        from src.gradio_app.services.dataset_service import DatasetService

        return DatasetService(tmp_path)

    def _make_zip(self, tmp_path: Path, name="demo"):
        import zipfile

        zip_path = tmp_path / f"{name}.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("demo/images/train/a.jpg", b"fake")
        return zip_path

    def test_extract_rejects_existing_without_overwrite(self, svc, tmp_path):
        target = svc.dataset_dir / "demo"
        target.mkdir(parents=True)
        (target / "keep.txt").write_text("precious", encoding="utf-8")

        result = svc.extract(str(self._make_zip(tmp_path)), "demo", overwrite=False)
        assert result["status"] == "exists"
        assert (target / "keep.txt").exists()  # 原数据未被触碰

    def test_extract_overwrites_with_flag(self, svc, tmp_path):
        target = svc.dataset_dir / "demo"
        target.mkdir(parents=True)
        (target / "keep.txt").write_text("old", encoding="utf-8")

        result = svc.extract(str(self._make_zip(tmp_path)), "demo", overwrite=True)
        assert result["status"] == "success"
        assert not (target / "keep.txt").exists()
        assert (target / "images" / "train" / "a.jpg").exists()


class TestClassificationConversion:
    @pytest.fixture()
    def svc(self, tmp_path):
        from src.gradio_app.services.dataset_service import DatasetService

        svc = DatasetService(tmp_path)
        # 构造分类格式数据集：images/train/{classA,classB}/
        for cls in ("classA", "classB"):
            d = svc.dataset_dir / "cls-ds" / "images" / "train" / cls
            d.mkdir(parents=True)
            (d / f"{cls}_1.png").write_bytes(b"fake-png")
            (d / f"{cls}_2.png").write_bytes(b"fake-png")
        yield svc

    def test_pending_conversion_detected(self, svc):
        assert "cls-ds" in svc.get_pending_conversion()

    def test_convert_success(self, svc):
        result = svc.convert("cls-ds")
        assert result["status"] == "success"
        assert result["converted_name"] == "cls-ds-yolo"

        converted = svc.dataset_dir / "cls-ds-yolo"
        assert (converted / "images" / "train").exists()
        assert (converted / "labels" / "train").exists()
        labels = list((converted / "labels" / "train").glob("*.txt"))
        assert len(labels) == 4  # 2 类 × 2 张

    def test_convert_keeps_original_by_default(self, svc):
        svc.convert("cls-ds")
        assert (svc.dataset_dir / "cls-ds").exists()

    def test_convert_delete_original(self, svc):
        result = svc.convert("cls-ds", delete_original=True)
        assert result["status"] == "success"
        assert not (svc.dataset_dir / "cls-ds").exists()

    def test_convert_rejects_missing_dataset(self, svc):
        result = svc.convert("no-such-dataset")
        assert result["status"] == "error"


# ----------------------------------------------------------------------
# P1-4/P1-5 监控组件
# ----------------------------------------------------------------------
class TestMonitorHelpers:
    def test_progress_bar_html(self):
        from src.gradio_app.components.training_monitor import _progress_bar

        html = _progress_bar(42.5, 95)
        assert "42.5%" in html
        assert "预计剩余 1 分 35 秒" in html
        assert "width: 42.5%" in html

    def test_format_eta_variants(self):
        from src.gradio_app.components.training_monitor import _format_eta

        assert _format_eta(None) == ""
        assert _format_eta(0) == "即将完成"
        assert "45 秒" in _format_eta(45)
        assert "2 分" in _format_eta(125)
        assert "1 时" in _format_eta(3750)

    def test_metric_card_uses_label(self):
        from src.gradio_app.components.training_monitor import _metric_card

        assert "Accuracy@1" in _metric_card("Accuracy@1", "0.90", "green")


# ----------------------------------------------------------------------
# 冒烟：Gradio 应用可构建
# ----------------------------------------------------------------------
def test_create_app_smoke():
    from src.gradio_app.app import create_app

    demo = create_app()
    assert demo is not None
