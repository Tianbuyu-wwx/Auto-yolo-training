"""
M1 管理面 API 验收测试（前端升级：REST + WebSocket）

覆盖：数据集 CRUD/上传/校验/转换、训练启动/停止/状态、run/对比、
任务队列、模型清单、注册表、WebSocket 流、SPA 静态托管。
"""

import io
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from src.api.admin import create_admin_app


@pytest.fixture()
def client(tmp_path):
    """管理面应用（进程内训练模式 + 队列 runner 不启动，保证测试确定性）"""
    app = create_admin_app(base_dir=tmp_path, use_subprocess=False, start_queue_runner=False)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def dummy_dataset(client, tmp_path):
    """在 API 的 base_dir 里造一个最小 YOLO 数据集"""
    from PIL import Image

    base = client.app.state.base_dir
    img_dir = base / "dataset" / "api-ds" / "images" / "train"
    lbl_dir = base / "dataset" / "api-ds" / "labels" / "train"
    img_dir.mkdir(parents=True)
    lbl_dir.mkdir(parents=True)
    for i in range(2):
        Image.new("RGB", (32, 32)).save(img_dir / f"img{i}.png")
        (lbl_dir / f"img{i}.txt").write_text("0 0.5 0.5 0.5 0.5\n", encoding="utf-8")
    (base / "dataset" / "api-ds" / "data.yaml").write_text(
        "nc: 1\nnames: [cat]\n", encoding="utf-8")
    return "api-ds"


# ----------------------------------------------------------------------
# 数据集
# ----------------------------------------------------------------------
class TestDatasetEndpoints:
    def test_list_and_info(self, client, dummy_dataset):
        r = client.get("/api/datasets")
        assert r.status_code == 200
        assert "api-ds" in r.json()["datasets"]

        r = client.get("/api/datasets/api-ds")
        assert r.status_code == 200
        info = r.json()
        assert info["total_images"] == 2
        assert info["splits"]["train"]["images"] == 2

    def test_info_404(self, client):
        assert client.get("/api/datasets/nope").status_code == 404

    def test_preview_original_and_boxes(self, client, dummy_dataset):
        r = client.get("/api/datasets/api-ds/preview")
        assert r.status_code == 200
        assert len(r.json()["images"]) == 2

        r = client.get("/api/datasets/api-ds/preview", params={"boxes": True})
        assert r.status_code == 200
        assert len(r.json()["images"]) == 2  # 画框缓存已生成

    def test_image_file_serving(self, client, dummy_dataset):
        r = client.get("/api/datasets/api-ds/images/train/img0.png")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/")

    def test_image_path_traversal_blocked(self, client, dummy_dataset):
        r = client.get("/api/datasets/api-ds/images/train/..%2F..%2Fdata.yaml")
        assert r.status_code in (404, 400)

    def test_upload_zip(self, client, tmp_path):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("up-ds/images/train/a.png", b"fake")
        buf.seek(0)
        r = client.post("/api/datasets/upload",
                        files={"file": ("up-ds.zip", buf, "application/zip")})
        assert r.status_code == 200
        assert r.json()["dataset_name"] == "up-ds"

        # 同名再传 → 409（覆盖保护），带 overwrite=true → 200
        buf.seek(0)
        r = client.post("/api/datasets/upload",
                        files={"file": ("up-ds.zip", buf, "application/zip")})
        assert r.status_code == 409
        buf.seek(0)
        r = client.post("/api/datasets/upload",
                        files={"file": ("up-ds.zip", buf, "application/zip")},
                        data={"overwrite": "true"})
        assert r.status_code == 200

    def test_validate(self, client, dummy_dataset):
        r = client.post("/api/datasets/api-ds/validate")
        assert r.status_code == 200
        assert r.json()["status"] in ("success", "warning")

    def test_convert_rejects_missing(self, client):
        r = client.post("/api/datasets/nope/convert")
        assert r.status_code == 400


# ----------------------------------------------------------------------
# 训练
# ----------------------------------------------------------------------
class TestTrainingEndpoints:
    def test_start_missing_dataset_fails_gracefully(self, client):
        # model 用清单外名字（不触发下载逻辑），数据集不存在 → worker 快速失败
        r = client.post("/api/trainings/start", json={
            "dataset_name": "no-such-ds", "model": "custom-weights.pt",
            "epochs": 1, "workers": 0,
        })
        assert r.status_code == 200
        assert r.json()["success"] is True

        # 进程内模式跑完快速失败
        for _ in range(60):
            status = client.get("/api/trainings/status").json()
            if not status["is_running"]:
                break
            time.sleep(0.2)
        assert status["is_running"] is False
        assert status["error_message"]

    def test_start_missing_catalog_model_400(self, client):
        """清单内模型未下载 → 400（不静默阻塞下载）"""
        r = client.post("/api/trainings/start", json={"dataset_name": "x"})
        assert r.status_code == 400
        assert "未下载" in r.json()["detail"]

    def test_start_conflict(self, client, tmp_path):
        # 挂一个"正在运行"的状态制造 409
        svc = client.app.state.services["training"]
        from src.gradio_app.models.training_state import TrainingState

        svc.state = TrainingState()
        svc.state.update(is_running=True)
        r = client.post("/api/trainings/start",
                        json={"dataset_name": "x", "model": "custom.pt"})
        assert r.status_code == 409

    def test_resume_from_reaches_config(self, client, dummy_dataset):
        """resume_from 必须落到 config.resume 上，否则管线根本不会走 resume 分支。

        resume 模式下管线仍把当前 config 的 dataset_name 显式传给
        `model.train(data=…)`，而 checkpoint 也要靠 `model` 传进去（管线是从
        cfg.model 解析模型路径的）。所以这里同时断言两者都透传 —— 只传
        resume_from 会"静默失效"：不报错，但也不会真的续训。
        """
        svc = client.app.state.services["training"]
        captured = {}

        def fake_start(cfg):
            captured["cfg"] = cfg
            return True

        svc.start = fake_start
        ckpt = "runs/detect/resume_auto/weights/last.pt"
        r = client.post("/api/trainings/start", json={
            "dataset_name": dummy_dataset,
            "model": ckpt,
            "resume_from": ckpt,
        })
        assert r.status_code == 200
        cfg = captured["cfg"]
        assert cfg.resume_from == ckpt
        assert cfg.model == ckpt
        assert cfg.to_overrides()["resume"] is True

    def test_stop_without_training_409(self, client):
        assert client.post("/api/trainings/stop").status_code == 409

    def test_runs_and_results(self, client, tmp_path):
        base = client.app.state.base_dir
        run = base / "runs" / "detect" / "cmp_auto"
        run.mkdir(parents=True)
        (run / "results.csv").write_text(
            "epoch,train/box_loss,metrics/mAP50(B),metrics/mAP50-95(B)\n"
            "9,0.5,0.77,0.55\n", encoding="utf-8")

        r = client.get("/api/trainings/runs")
        assert "cmp_auto" in r.json()["runs"]

        r = client.get("/api/trainings/results", params={"run": "cmp_auto"})
        assert r.status_code == 200
        body = r.json()
        assert body["final_metrics"]["primary"]["mAP@50"] == 0.77

        r = client.get("/api/trainings/results", params={"run": "ghost"})
        assert r.status_code == 404

    def test_checkpoint_details(self, client, tmp_path):
        """断点列表要带出数据集与进度。

        续训时管线仍以**当前** config 的 dataset_name 传 data=，接错数据集不会报错，
        只会在别的数据上接着练。所以界面必须知道每个断点属于哪个数据集、练到第几轮。
        路径刻意用 Windows 反斜杠 —— args.yaml 是训练所在平台写出的，反斜杠在 POSIX
        上不是分隔符，这里同时锁住跨平台解析。
        """
        base = client.app.state.base_dir
        run = base / "runs" / "detect" / "resume_auto"
        (run / "weights").mkdir(parents=True)
        (run / "weights" / "last.pt").write_bytes(b"\x00" * 1024)
        (run / "args.yaml").write_text(
            "task: detect\n"
            "model: yolov8n.pt\n"
            r"data: E:\ds\configs\models\data_my-ds.yaml" + "\n"
            "epochs: 150\n",
            encoding="utf-8")
        # 3 个 epoch 行 + 表头 → 已完成 3 轮
        (run / "results.csv").write_text(
            "epoch,train/box_loss,metrics/mAP50(B)\n"
            "0,1.2,0.11\n1,1.0,0.22\n2,0.9,0.33\n",
            encoding="utf-8")

        r = client.get("/api/trainings/runs")
        assert r.status_code == 200
        body = r.json()
        assert "resume_auto" in body["runs"]
        detail = next(d for d in body["checkpoint_details"] if d["run"] == "resume_auto")
        assert detail["dataset"] == "my-ds"
        assert detail["epochs_done"] == 3
        assert detail["epochs_planned"] == 150
        assert detail["modified"]
        assert "mtime" not in detail          # 排序用的内部字段不外泄
        # checkpoints 是 details 的投影，两者必须一致
        assert detail["path"] in body["checkpoints"]
        assert len(body["checkpoints"]) == len(body["checkpoint_details"])

    def test_compare(self, client):
        base = client.app.state.base_dir
        run = base / "runs" / "detect" / "cmp_auto"
        run.mkdir(parents=True)
        (run / "results.csv").write_text(
            "epoch,train/box_loss,metrics/mAP50(B),metrics/mAP50-95(B)\n9,0.5,0.77,0.55\n",
            encoding="utf-8")
        r = client.get("/api/trainings/compare")
        assert r.status_code == 200
        assert "cmp_auto" in r.json()["markdown"]


# ----------------------------------------------------------------------
# 任务队列
# ----------------------------------------------------------------------
class TestQueueEndpoints:
    def test_enqueue_list_cancel(self, client):
        r = client.post("/api/queue/enqueue", json={
            "dataset_name": "ds-a", "model": "custom-weights.pt", "epochs": 5,
        })
        assert r.status_code == 200
        task_id = r.json()["task_id"]

        tasks = client.get("/api/queue/tasks").json()["tasks"]
        assert tasks[0]["id"] == task_id
        assert tasks[0]["status"] == "queued"
        assert tasks[0]["config"]["epochs"] == 5

        r = client.post(f"/api/queue/{task_id}/cancel")
        assert r.status_code == 200
        assert client.get("/api/queue/tasks").json()["tasks"][0]["status"] == "cancelled"

        assert client.post("/api/queue/9999/cancel").status_code == 409


# ----------------------------------------------------------------------
# 模型 / 注册表 / 导出
# ----------------------------------------------------------------------
class TestModelAndRegistry:
    def test_model_catalog_filter(self, client):
        r = client.get("/api/models", params={"task": "segment"})
        models = r.json()["models"]
        assert models and all(m["task"] == "segment" for m in models)
        assert any(m["filename"] == "yolov8n-seg.pt" for m in models)

    def test_model_download_unknown_400(self, client):
        r = client.post("/api/models/download", data={"filename": "ghost.pt"})
        assert r.status_code == 400

    def test_registry_and_export(self, client):
        base = client.app.state.base_dir
        # 注册一个版本
        from src.model_registry import ModelRegistry

        weights = base / "runs" / "detect" / "reg_auto" / "weights" / "best.pt"
        weights.parent.mkdir(parents=True)
        weights.write_bytes(b"fake")
        ModelRegistry(str(base)).register(model_path=str(weights), dataset_name="regds",
                                          metrics={"mAP50": 0.8}, copy_model=False)

        r = client.get("/api/registry")
        assert "regds" in r.json()["datasets"]

        # 导出 run 不存在 → 404
        r = client.post("/api/exports", json={"run_name": "ghost", "fmt": "onnx"})
        assert r.status_code == 404


# ----------------------------------------------------------------------
# WebSocket + 静态托管
# ----------------------------------------------------------------------
class TestWsAndStatic:
    def test_training_ws_stream(self, client):
        with client.websocket_connect("/ws/training") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "training"
            assert "is_running" in msg["status"]
            assert isinstance(msg["logs"], str)

    def test_index_without_frontend_build(self, client):
        r = client.get("/")
        # frontend/dist 不存在时返回提示 JSON
        if r.headers["content-type"].startswith("application/json"):
            assert "frontend" in r.json()["hint"]
        else:
            assert r.status_code == 200
