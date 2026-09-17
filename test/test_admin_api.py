"""
M1 管理面 API 验收测试（前端升级：REST + WebSocket）

覆盖：数据集 CRUD/上传/校验/转换、训练启动/停止/状态、run/对比、
任务队列、模型清单、注册表、WebSocket 流、SPA 静态托管。
"""

import io
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.admin import create_admin_app


@pytest.fixture()
def client(tmp_path):
    """管理面应用（进程内训练模式 + 队列 runner 不启动，保证测试确定性）

    ``api_key=""`` 是显式关闭认证：不显式传的话会去读 ``YOLO_API_KEY`` /
    settings，于是「本机导出了 key」的开发机上整套测试会突然 401。
    """
    app = create_admin_app(
        base_dir=tmp_path, use_subprocess=False, start_queue_runner=False, api_key=""
    )
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
        "nc: 1\nnames: [cat]\n", encoding="utf-8"
    )
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
        r = client.post(
            "/api/datasets/upload", files={"file": ("up-ds.zip", buf, "application/zip")}
        )
        assert r.status_code == 200
        assert r.json()["dataset_name"] == "up-ds"

        # 同名再传 → 409（覆盖保护），带 overwrite=true → 200
        buf.seek(0)
        r = client.post(
            "/api/datasets/upload", files={"file": ("up-ds.zip", buf, "application/zip")}
        )
        assert r.status_code == 409
        buf.seek(0)
        r = client.post(
            "/api/datasets/upload",
            files={"file": ("up-ds.zip", buf, "application/zip")},
            data={"overwrite": "true"},
        )
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
        r = client.post(
            "/api/trainings/start",
            json={
                "dataset_name": "no-such-ds",
                "model": "custom-weights.pt",
                "epochs": 1,
                "workers": 0,
            },
        )
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
        r = client.post("/api/trainings/start", json={"dataset_name": "x", "model": "custom.pt"})
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
        r = client.post(
            "/api/trainings/start",
            json={
                "dataset_name": dummy_dataset,
                "model": ckpt,
                "resume_from": ckpt,
            },
        )
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
            "epoch,train/box_loss,metrics/mAP50(B),metrics/mAP50-95(B)\n9,0.5,0.77,0.55\n",
            encoding="utf-8",
        )

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
            encoding="utf-8",
        )
        # 3 个 epoch 行 + 表头 → 已完成 3 轮
        (run / "results.csv").write_text(
            "epoch,train/box_loss,metrics/mAP50(B)\n0,1.2,0.11\n1,1.0,0.22\n2,0.9,0.33\n",
            encoding="utf-8",
        )

        r = client.get("/api/trainings/runs")
        assert r.status_code == 200
        body = r.json()
        assert "resume_auto" in body["runs"]
        detail = next(d for d in body["checkpoint_details"] if d["run"] == "resume_auto")
        assert detail["dataset"] == "my-ds"
        assert detail["epochs_done"] == 3
        assert detail["epochs_planned"] == 150
        assert detail["modified"]
        assert "mtime" not in detail  # 排序用的内部字段不外泄
        # checkpoints 是 details 的投影，两者必须一致
        assert detail["path"] in body["checkpoints"]
        assert len(body["checkpoints"]) == len(body["checkpoint_details"])

    def test_compare(self, client):
        base = client.app.state.base_dir
        run = base / "runs" / "detect" / "cmp_auto"
        run.mkdir(parents=True)
        (run / "results.csv").write_text(
            "epoch,train/box_loss,metrics/mAP50(B),metrics/mAP50-95(B)\n9,0.5,0.77,0.55\n",
            encoding="utf-8",
        )
        r = client.get("/api/trainings/compare")
        assert r.status_code == 200
        assert "cmp_auto" in r.json()["markdown"]


# ----------------------------------------------------------------------
# 任务队列
# ----------------------------------------------------------------------
class TestQueueEndpoints:
    def test_enqueue_list_cancel(self, client):
        r = client.post(
            "/api/queue/enqueue",
            json={
                "dataset_name": "ds-a",
                "model": "custom-weights.pt",
                "epochs": 5,
            },
        )
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
        ModelRegistry(str(base)).register(
            model_path=str(weights), dataset_name="regds", metrics={"mAP50": 0.8}, copy_model=False
        )

        r = client.get("/api/registry")
        assert "regds" in r.json()["datasets"]

        # 导出 run 不存在 → 404
        r = client.post("/api/exports", json={"run_name": "ghost", "fmt": "onnx"})
        assert r.status_code == 404


# ----------------------------------------------------------------------
# 模型注册表写端点（G-4）
# ----------------------------------------------------------------------
@pytest.fixture()
def reg_run(client):
    """造一个带 best.pt / last.pt / results.csv 的 run。

    模块级（不是挂在某个测试类里）：注册表的两组用例都要用它 ——
    ``TestRegistryEndpoints`` 的读写，以及 ``TestRegistryWeightsMissing``
    的「权重被清理后」状态。
    """
    base = client.app.state.base_dir
    run = base / "runs" / "detect" / "reg_run"
    (run / "weights").mkdir(parents=True)
    (run / "weights" / "best.pt").write_bytes(b"fake-best")
    (run / "weights" / "last.pt").write_bytes(b"fake-last")
    (run / "results.csv").write_text(
        "epoch,time,metrics/precision(B),metrics/recall(B),"
        "metrics/mAP50(B),metrics/mAP50-95(B)\n"
        "1,1.0,0.5,0.4,0.50,0.30\n"
        "2,2.0,0.7,0.6,0.80,0.60\n",
        encoding="utf-8",
    )
    return "reg_run"


class TestRegistryEndpoints:
    def _register(self, client, dataset="regds", run="reg_run", **kw):
        r = client.post(
            "/api/registry/register", json={"dataset_name": dataset, "run_name": run, **kw}
        )
        assert r.status_code == 200, r.text
        return r.json()

    def _versions(self, client, dataset="regds"):
        r = client.get(f"/api/registry/{dataset}")
        assert r.status_code == 200, r.text
        return r.json()["versions"]

    def test_register_autofills_metrics_from_results_csv(self, client, reg_run):
        """手抄 mAP 既麻烦又易错 —— 从 run 的 results.csv 自动补最终指标"""
        body = self._register(client, tags=["baseline"])
        assert body["metrics_auto_filled"] is True
        v = body["version"]
        # 取的是最后一行（epoch 2），不是第一行
        assert v["metrics"]["mAP50"] == 0.8
        assert v["metrics"]["mAP50_95"] == 0.6
        # 只保留规范键，避免对比表出现 "mAP@50" 同义重复行
        assert set(v["metrics"]) == {"mAP50", "mAP50_95"}
        assert v["status"] == "staging"
        assert v["tags"] == ["baseline"]

    def test_register_uses_explicit_metrics_when_given(self, client, reg_run):
        body = self._register(client, metrics={"mAP50": 0.123})
        assert body["metrics_source"] == "request"
        assert body["version"]["metrics"] == {"mAP50": 0.123}

    def test_register_last_weights(self, client, reg_run):
        v = self._register(client, weights="last")["version"]
        assert Path(v["model_path"]).name == "last.pt"

    def test_register_missing_weights_404(self, client, reg_run):
        r = client.post(
            "/api/registry/register", json={"dataset_name": "regds", "run_name": "ghost_run"}
        )
        assert r.status_code == 404

    def test_register_rejects_path_traversal(self, client, reg_run):
        """run_name 来自请求体，不能借 ../ 把权重指到 runs/ 之外"""
        r = client.post(
            "/api/registry/register", json={"dataset_name": "regds", "run_name": "../../src"}
        )
        assert r.status_code == 400

    def test_register_rejects_outside_model_path(self, client, reg_run, tmp_path):
        r = client.post(
            "/api/registry/register",
            json={"dataset_name": "regds", "model_path": str(tmp_path / "outside.pt")},
        )
        assert r.status_code == 400

    def test_register_requires_a_source(self, client, reg_run):
        r = client.post("/api/registry/register", json={"dataset_name": "regds"})
        assert r.status_code == 400

    def test_register_requires_dataset_name(self, client, reg_run):
        r = client.post(
            "/api/registry/register", json={"dataset_name": "   ", "run_name": "reg_run"}
        )
        assert r.status_code == 400

    def test_versions_404_for_unknown_dataset(self, client):
        assert client.get("/api/registry/nope").status_code == 404

    def test_empty_tag_list_rejected(self, client, reg_run):
        v = self._register(client)["version"]
        r = client.post(f"/api/registry/regds/{v['version_id']}/tags", json={"tags": ["  "]})
        assert r.status_code == 400

    def test_status_whitelist(self, client, reg_run):
        v = self._register(client)["version"]
        vid = v["version_id"]
        r = client.post(f"/api/registry/regds/{vid}/status", json={"status": "banana"})
        assert r.status_code == 400
        r = client.post(f"/api/registry/regds/{vid}/status", json={"status": "archived"})
        assert r.status_code == 200
        assert self._versions(client)[0]["status"] == "archived"

    def test_missing_version_404(self, client, reg_run):
        assert (
            client.post("/api/registry/regds/nope/status", json={"status": "archived"}).status_code
            == 404
        )
        assert client.post("/api/registry/regds/nope/promote").status_code == 404
        assert client.delete("/api/registry/regds/nope").status_code == 404

    def test_promote_archives_previous_production(self, client, reg_run):
        """一个数据集只能有一个生产版本；晋升新的应把旧的降为 archived"""
        v1 = self._register(client, tags=["v1"])["version"]
        v2 = self._register(client, tags=["v2"])["version"]

        r = client.post(f"/api/registry/regds/{v1['version_id']}/promote")
        assert r.status_code == 200
        assert r.json()["archived"] == []

        r = client.post(f"/api/registry/regds/{v2['version_id']}/promote")
        assert r.status_code == 200
        assert r.json()["archived"] == [v1["version_id"]]

        by_id = {v["version_id"]: v for v in self._versions(client)}
        assert by_id[v1["version_id"]]["status"] == "archived"
        assert by_id[v2["version_id"]]["status"] == "production"
        assert client.get("/api/registry/regds").json()["production_model"]

    def test_add_tags_dedupes(self, client, reg_run):
        v = self._register(client, tags=["a"])["version"]
        r = client.post(
            f"/api/registry/regds/{v['version_id']}/tags", json={"tags": ["a", "b", " b "]}
        )
        assert r.status_code == 200
        assert sorted(r.json()["tags"]) == ["a", "b"]

    def test_compare_versions(self, client, reg_run):
        v1 = self._register(client, metrics={"mAP50": 0.5})["version"]
        v2 = self._register(client, metrics={"mAP50": 0.8})["version"]
        r = client.get(
            "/api/registry/regds/compare", params={"a": v1["version_id"], "b": v2["version_id"]}
        )
        assert r.status_code == 200
        diff = r.json()["metrics_diff"]["mAP50"]
        assert diff["v1"] == 0.5 and diff["v2"] == 0.8
        assert diff["diff"] == pytest.approx(0.3)

        r = client.get("/api/registry/regds/compare", params={"a": v1["version_id"], "b": "nope"})
        assert r.status_code == 404

    def test_delete_staging_keeps_weights_on_disk(self, client, reg_run):
        """注册记录 ≠ 权重文件：删记录不该动 runs/ 下的原位权重"""
        v = self._register(client)["version"]
        weights = Path(v["model_path"])
        assert weights.is_file()

        r = client.delete(f"/api/registry/regds/{v['version_id']}")
        assert r.status_code == 200
        assert r.json()["deleted_registry_copy"] is False
        assert r.json()["weights_path"] == str(weights)
        assert weights.is_file(), "原位权重被误删"
        assert client.get("/api/registry/regds").status_code == 404

    def test_delete_copied_version_removes_only_the_copy(self, client, reg_run):
        """copy_model=True 时删的是注册表内的副本，原位权重必须还在"""
        v = self._register(client, copy_model=True)["version"]
        copy_path = Path(v["model_path"])
        assert copy_path.is_file()
        assert "model_registry" in str(copy_path)

        r = client.delete(f"/api/registry/regds/{v['version_id']}")
        assert r.status_code == 200
        assert r.json()["deleted_registry_copy"] is True
        assert not copy_path.exists(), "注册表副本应被删除"
        assert (
            client.app.state.base_dir / "runs" / "detect" / "reg_run" / "weights" / "best.pt"
        ).is_file(), "原位权重被误删"

    def test_production_version_cannot_be_deleted(self, client, reg_run):
        v = self._register(client)["version"]
        client.post(f"/api/registry/regds/{v['version_id']}/promote")
        r = client.delete(f"/api/registry/regds/{v['version_id']}")
        assert r.status_code == 409
        # 409 之后必须仍然查得到，不能删了一半
        assert client.get("/api/registry/regds").status_code == 200

    def test_same_second_registrations_get_distinct_ids(self, client, reg_run):
        """时间戳只到秒、文件名都是 best.pt —— id 撞车会把两条记录绑成一个副本目录"""
        v1 = self._register(client, copy_model=True)["version"]
        v2 = self._register(client, copy_model=True)["version"]
        assert v1["version_id"] != v2["version_id"]
        assert Path(v1["model_path"]).is_file()
        assert Path(v2["model_path"]).is_file()


# ----------------------------------------------------------------------
# 数据集删除 / 回收站（G-5）
# ----------------------------------------------------------------------
class TestRecycleBin:
    def _recycle_items(self, client):
        r = client.get("/api/recycle")
        assert r.status_code == 200, r.text
        return r.json()["items"]

    def test_delete_moves_to_recycle_not_rmtree(self, client, dummy_dataset):
        """删数据集必须是「移到回收目录」，不是抹掉 —— 一次误点不该不可逆"""
        base = client.app.state.base_dir
        ds_dir = base / "dataset" / "api-ds"
        assert ds_dir.is_dir()

        r = client.delete("/api/datasets/api-ds")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "success"
        assert Path(body["recycled_to"]).is_dir()
        assert not ds_dir.exists()

        # 关键：数据还在磁盘上，且能被列出来
        items = self._recycle_items(client)
        assert len(items) == 1
        assert items[0]["original_name"] == "api-ds"

    def test_recycled_dir_is_not_listed_as_a_dataset(self, client, dummy_dataset):
        """回收目录以 . 开头，扫描器必须跳过它 —— 否则会出现一个叫 .recycle 的假数据集"""
        client.delete("/api/datasets/api-ds")
        payload = client.get("/api/datasets").json()
        names = payload["datasets"]
        assert "api-ds" not in names
        assert not any(".recycle" in n for n in names)

        # 只断言 datasets 是不够的：.recycle 里没有 data.yaml，list_ready_datasets
        # 天然不会列出它，上面那条恒真、没有辨别力。真正的风险在 statuses ——
        # 它走 scan_all_datasets，会把回收目录当成一个数据集去分析，
        # 界面上就凭空多出一个「格式未知」的假数据集。
        status_names = [s["name"] for s in payload["statuses"]]
        assert not any(".recycle" in n for n in status_names), status_names

    def test_restore_brings_the_dataset_back(self, client, dummy_dataset):
        client.delete("/api/datasets/api-ds")
        recycled = self._recycle_items(client)[0]["recycled_name"]

        r = client.post(f"/api/recycle/{recycled}/restore")
        assert r.status_code == 200, r.text
        assert self._recycle_items(client) == []

        # 恢复后要重新成为「可训练」（data.yaml 还在）
        ds = client.get("/api/datasets").json()
        assert "api-ds" in ds["datasets"]
        status = next(s for s in ds["statuses"] if s["name"] == "api-ds")
        assert status["is_trainable"] is True

    def test_restore_conflicts_with_existing_dir(self, client, dummy_dataset):
        client.delete("/api/datasets/api-ds")
        recycled = self._recycle_items(client)[0]["recycled_name"]
        # 重建同名数据集后再恢复 → 不能静默覆盖
        (client.app.state.base_dir / "dataset" / "api-ds").mkdir(parents=True)
        r = client.post(f"/api/recycle/{recycled}/restore")
        assert r.status_code == 400

    def test_delete_unknown_404(self, client):
        assert client.delete("/api/datasets/nope").status_code == 404

    def test_restore_unknown_404(self, client):
        assert client.post("/api/recycle/nope/restore").status_code == 404

    def test_delete_blocked_while_training(self, client, dummy_dataset):
        """训练中途把数据集抽走，报错和"删数据集"看不出关系，所以直接拦下"""
        svc = client.app.state.services["training"]
        svc.state.update(is_running=True)
        try:
            r = client.delete("/api/datasets/api-ds")
            assert r.status_code == 409
            assert (client.app.state.base_dir / "dataset" / "api-ds").is_dir()
        finally:
            svc.state.update(is_running=False)

        assert client.delete("/api/datasets/api-ds").status_code == 200

    @pytest.mark.parametrize("bad", ["..", "../src", "..%2Fsrc", "%2E%2E%2Fsrc"])
    def test_delete_rejects_path_traversal(self, client, dummy_dataset, bad):
        """客户端会把 `..` 规范化掉，请求根本到不了处理函数（实测 405 Method Not Allowed）。

        也就是说这里有两层防御：URL 规范化 + 服务层的越界检查。断言"没到 2xx"
        并且**目标没被动过**，才是这条用例真正要保证的东西。
        """
        r = client.delete(f"/api/datasets/{bad}")
        assert r.status_code not in (200, 204), r.text
        assert (client.app.state.base_dir / "dataset" / "api-ds").is_dir()

    def test_service_rejects_traversal_names(self, client, dummy_dataset):
        """直接打服务层（绕开 URL 规范化）：越界名必须被拒，且不得移动任何东西"""
        base = client.app.state.base_dir
        outside = base / "outside_probe"
        outside.mkdir()
        (outside / "keep.txt").write_text("keep", encoding="utf-8")

        svc = client.app.state.services["dataset"]
        for bad in (
            "..",
            "../src",
            "../outside_probe",
            "api-ds/../../outside_probe",
            "",
            ".",
            "dataset",
        ):
            res = svc.delete(bad)
            assert res["status"] == "error", f"{bad!r} 未被拒绝"

        # dataset/ 内外都得原样在，且被拒绝的删除不该在回收目录里留下任何东西
        assert (base / "dataset" / "api-ds").is_dir()
        assert (outside / "keep.txt").is_file()
        recycle = base / "dataset" / ".recycle"
        assert not recycle.exists() or not any(recycle.iterdir()), "被拒绝的删除却写进了回收目录"


# ----------------------------------------------------------------------
# 管理面 API Key 认证（G-2 · 方案 A）
# ----------------------------------------------------------------------
AUTH_KEY = "s3cret-key"


@pytest.fixture()
def auth_client(tmp_path):
    """开启了 API Key 认证的管理面应用"""
    app = create_admin_app(
        base_dir=tmp_path, use_subprocess=False, start_queue_runner=False, api_key=AUTH_KEY
    )
    with TestClient(app) as c:
        yield c


class TestAdminAuth:
    """方案 A：未配置 key 则不校验；配了 key 就拦下所有 /api/* 与 WS"""

    def test_unconfigured_key_means_no_auth(self, client):
        """未配置 key 时一个受保护端点也不该拦 —— 本地开发零摩擦是这条方案的取舍"""
        assert client.get("/api/datasets").status_code == 200
        assert client.get("/api/health").json()["auth_enabled"] is False

    def test_api_requires_key_when_configured(self, auth_client):
        r = auth_client.get("/api/datasets")
        assert r.status_code == 401, r.text
        assert r.json()["detail"] == "Invalid or missing API Key"

    def test_correct_key_is_accepted(self, auth_client):
        r = auth_client.get("/api/datasets", headers={"X-API-Key": AUTH_KEY})
        assert r.status_code == 200, r.text

    def test_wrong_key_is_rejected(self, auth_client):
        r = auth_client.get("/api/datasets", headers={"X-API-Key": "nope"})
        assert r.status_code == 401

    def test_health_stays_open(self, auth_client):
        """存活探针不该需要凭据，否则外部无法判断服务是否起来"""
        r = auth_client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["auth_enabled"] is True

    def test_write_endpoints_are_also_guarded(self, auth_client, dummy_dataset):
        """启停训练、删除数据集这些有副作用的端点必须跟读端点一样被拦"""
        assert auth_client.post("/api/trainings/stop").status_code == 401
        assert auth_client.delete("/api/datasets/api-ds").status_code == 401
        # 被拦下就不能真的删掉
        assert (auth_client.app.state.base_dir / "dataset" / "api-ds").is_dir()

    def test_api_docs_are_reachable_without_key(self, auth_client):
        """Swagger UI 由浏览器直接打开，带不了请求头 —— 拦掉等于给一个死链接"""
        assert auth_client.get("/api/docs").status_code == 200
        assert auth_client.get("/api/openapi.json").status_code == 200

    def test_spa_shell_is_not_guarded(self, auth_client):
        """静态资源是 SPA 本身，拦掉的话浏览器连输入 key 的界面都加载不出来"""
        r = auth_client.get("/")
        assert r.status_code != 401

    def test_ws_requires_key(self, auth_client):
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises(WebSocketDisconnect) as exc:
            with auth_client.websocket_connect("/ws/training") as ws:
                ws.receive_text()
        assert exc.value.code == 1008

    def test_ws_accepts_key_via_query_param(self, auth_client):
        """浏览器没法给 WebSocket 设请求头，只能走查询参数"""
        with auth_client.websocket_connect(f"/ws/training?api_key={AUTH_KEY}") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "training"

    def test_ws_rejects_wrong_query_key(self, auth_client):
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises(WebSocketDisconnect):
            with auth_client.websocket_connect("/ws/training?api_key=wrong") as ws:
                ws.receive_text()

    def test_resolve_api_key_semantics(self, monkeypatch):
        """None = 去读环境；"" = 显式关闭 —— 这两档不能混"""
        from src.api.admin import resolve_api_key

        assert resolve_api_key("") == ""
        assert resolve_api_key("given") == "given"

        monkeypatch.setenv("YOLO_API_KEY", "from-env")
        assert resolve_api_key(None) == "from-env"

    def test_env_key_enables_auth_by_default(self, tmp_path, monkeypatch):
        """只设环境变量、不传参数时也必须真的生效 —— 否则方案 A 形同虚设"""
        monkeypatch.setenv("YOLO_API_KEY", "env-key")
        app = create_admin_app(
            base_dir=tmp_path, use_subprocess=False, start_queue_runner=False, api_key=None
        )
        with TestClient(app) as c:
            assert c.get("/api/health").json()["auth_enabled"] is True
            assert c.get("/api/datasets").status_code == 401
            assert c.get("/api/datasets", headers={"X-API-Key": "env-key"}).status_code == 200


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


# ----------------------------------------------------------------------
# 权重被清理后的注册表状态（2026-09-17）
# ----------------------------------------------------------------------
class TestRegistryWeightsMissing:
    """记录在、权重没了 —— 注册表必须显式说出来。

    真实背景：仓库自己的 model_registry/versions.json 里就有 1/4 条记录指向已被
    滚动清理的 run（copy_model=False 是默认注册方式，而 runs/ 只保留最近若干轮）。
    这类死链接不会让任何测试变红，只能靠显式标注 + 拒绝晋升来暴露。
    """

    @pytest.fixture()
    def stale_version(self, client, reg_run):
        """注册一个版本，然后把该 run 删掉，模拟「训练产物被滚动清理」"""
        import shutil

        r = client.post(
            "/api/registry/register", json={"dataset_name": "regds", "run_name": reg_run}
        )
        assert r.status_code == 200, r.text
        version = r.json()["version"]
        shutil.rmtree(client.app.state.base_dir / "runs" / "detect" / reg_run)
        return version

    def _register_live(self, client, reg_run):
        r = client.post(
            "/api/registry/register", json={"dataset_name": "regds", "run_name": reg_run}
        )
        assert r.status_code == 200, r.text
        return r.json()["version"]

    def test_healthy_version_is_not_flagged(self, client, reg_run):
        self._register_live(client, reg_run)
        versions = client.get("/api/registry/regds").json()["versions"]
        assert versions[0]["weights_missing"] is False

    def test_listing_flags_missing_weights(self, client, stale_version):
        """列表与详情两个入口都要标出来（控制台两处都会渲染）"""
        datasets = client.get("/api/registry").json()["datasets"]
        assert datasets["regds"][0]["weights_missing"] is True

        body = client.get("/api/registry/regds").json()
        assert body["versions"][0]["weights_missing"] is True
        assert body["production_model_available"] is False

    def test_promote_refuses_when_weights_are_gone(self, client, stale_version):
        """晋升必须被挡下：否则生产指针指向一个加载不了的路径，而且不会报错"""
        r = client.post(f"/api/registry/regds/{stale_version['version_id']}/promote")
        assert r.status_code == 409, r.text
        assert "权重" in r.json()["detail"]
        assert client.get("/api/registry/regds").json()["production_model"] is None

    def test_promote_still_works_for_a_live_version(self, client, reg_run):
        """守卫不能误伤：权重还在的版本照常晋升，且生产可用性为真"""
        version = self._register_live(client, reg_run)
        assert (
            client.post(f"/api/registry/regds/{version['version_id']}/promote").status_code == 200
        )
        body = client.get("/api/registry/regds").json()
        assert body["production_model_available"] is True
