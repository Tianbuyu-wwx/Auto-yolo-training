"""启动器扩展能力测试：推理管理 / 受控打开 / 诊断包 / 回收站 purge / 扩展端点。

不真启动推理子进程（那在 e2e 阶段做）；这里覆盖纯逻辑与端点契约。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = REPO_ROOT / "src" / "launcher" / "static"

from src.launcher import features  # noqa: E402
from src.launcher.backend import LauncherBackend  # noqa: E402


# ---------------- open_path ----------------

def test_open_path_rejects_outside_whitelist(tmp_path):
    res = features.open_path("../outside", tmp_path)
    assert res["status"] == "error"
    assert "仅允许" in res["message"]


def test_open_path_empty_rejected(tmp_path):
    assert features.open_path("", tmp_path)["status"] == "error"


def test_open_path_ok_within_whitelist(monkeypatch, tmp_path):
    opened: list[str] = []
    monkeypatch.setattr(features.os, "startfile", lambda p: opened.append(p), raising=False)
    res = features.open_path("artifacts/logs", tmp_path)  # 不存在会自动创建目录
    assert res["status"] == "ok"
    assert opened and (tmp_path / "artifacts" / "logs").is_dir()


def test_open_path_nested_allowed(monkeypatch, tmp_path):
    opened: list[str] = []
    monkeypatch.setattr(features.os, "startfile", lambda p: opened.append(p), raising=False)
    target = tmp_path / "artifacts" / "runs" / "detect"
    target.mkdir(parents=True)
    res = features.open_path("artifacts/runs/detect", tmp_path)
    assert res["status"] == "ok" and opened


def test_open_path_missing_file_errors(tmp_path):
    res = features.open_path("artifacts/runs/nonexistent.txt", tmp_path)
    assert res["status"] == "error"


# ---------------- diag_pack ----------------

def test_diag_pack_creates_zip(tmp_path):
    (tmp_path / "artifacts" / "logs").mkdir(parents=True)
    (tmp_path / "artifacts" / "logs" / "launcher.log").write_text("hello", encoding="utf-8")
    (tmp_path / "artifacts" / "runs" / "detect" / "run-a").mkdir(parents=True)
    res = features.diag_pack(tmp_path)
    assert res["status"] == "ok" and res["bytes"] > 0
    with zipfile.ZipFile(res["file"]) as zf:
        names = zf.namelist()
    assert "logs/launcher.log" in names
    assert "env-report.json" in names
    assert "runs-snapshot.json" in names


# ---------------- InferenceManager（不真启动） ----------------

def test_inference_status_idle(tmp_path):
    mgr = features.InferenceManager(tmp_path)
    st = mgr.status()
    assert st["running"] is False and st["pid"] is None


def test_inference_start_without_models_errors(tmp_path):
    mgr = features.InferenceManager(tmp_path)
    res = mgr.start()
    assert res["status"] == "error"
    assert "模型" in res["message"]


def test_inference_stop_when_not_running(tmp_path):
    mgr = features.InferenceManager(tmp_path)
    assert mgr.stop()["status"] == "not_running"


def test_inference_discovers_latest_best(tmp_path):
    best_a = tmp_path / "artifacts" / "runs" / "detect" / "run-a" / "weights"
    best_a.mkdir(parents=True)
    pa = best_a / "best.pt"
    pa.write_bytes(b"x")
    mgr = features.InferenceManager(tmp_path)
    assert mgr._discover_model() == str(pa)


# ---------------- 扩展端点（走真后端） ----------------

@pytest.fixture()
def backend(tmp_path):
    b = LauncherBackend(base_dir=tmp_path, frontend_dist=STATIC_DIR, start_queue_runner=False)
    b.start(ready_timeout=20)
    yield b
    b.stop()


def _post(url: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def test_inference_endpoints_contract(backend):
    with urllib.request.urlopen(f"{backend.url}/api/inference/status", timeout=5) as resp:
        st = json.loads(resp.read())
    assert st["running"] is False

    # 无模型 → 400 + 中文报错
    with pytest.raises(urllib.error.HTTPError) as ei:
        _post(f"{backend.url}/api/inference/start")
    assert ei.value.code == 400
    assert "模型" in json.loads(ei.value.read())["detail"]

    assert _post(f"{backend.url}/api/inference/stop")["status"] == "not_running"


def test_open_path_endpoint_contract(backend, monkeypatch):
    monkeypatch.setattr("src.launcher.features.os.startfile", lambda p: None, raising=False)
    res = _post(f"{backend.url}/api/launcher/open-path?rel_path=artifacts/logs")
    assert res["status"] == "ok"
    with pytest.raises(urllib.error.HTTPError) as ei:
        _post(f"{backend.url}/api/launcher/open-path?rel_path=../etc")
    assert ei.value.code == 400


def test_diag_pack_endpoint(backend):
    res = _post(f"{backend.url}/api/launcher/diag-pack")
    assert res["status"] == "ok"
    assert Path(res["file"]).is_file()


def test_recycle_purge_endpoint(backend, tmp_path):
    recycle = tmp_path / "dataset" / ".recycle"
    (recycle / "old_ds_20260101").mkdir(parents=True)
    (recycle / "old_ds_20260101" / "data.yaml").write_text("x", encoding="utf-8")
    res = _post(f"{backend.url}/api/recycle/purge")
    assert res["status"] == "ok" and res["removed"] == 1
    assert not (recycle / "old_ds_20260101").exists()

    # 单项 purge
    (recycle / "one_20260102").mkdir(parents=True)
    res2 = _post(f"{backend.url}/api/recycle/purge?name=one_20260102")
    assert res2["removed"] == 1
