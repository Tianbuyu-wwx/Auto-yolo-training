"""启动器壳（无 GUI 部分）：单实例锁 / 端口选择 / 内嵌后端起停 / 静态托管 override。

GUI 窗口本身由冒烟脚本验收（win_shot 截图 + 句柄探测，见 launcher-plan §Phase 1），
不在这里跑 —— CI 无桌面环境。本文件只覆盖 Python 层可断言的部分。
"""

from __future__ import annotations

import json
import socket
import sys
import time
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = REPO_ROOT / "src" / "launcher" / "static"

from src.launcher import app as launcher_app  # noqa: E402
from src.launcher.backend import LauncherBackend, pick_free_port  # noqa: E402


def test_pick_free_port_returns_bindable_port():
    port = pick_free_port()
    assert 1024 < port < 65536
    with socket.socket() as s:  # 随即绑定应成功（真空闲）
        s.bind(("127.0.0.1", port))


def test_pick_free_port_prefers_requested():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        free = s.getsockname()[1]
    assert pick_free_port(preferred=free) == free


@pytest.fixture()
def backend(tmp_path):
    b = LauncherBackend(base_dir=tmp_path, frontend_dist=STATIC_DIR, start_queue_runner=False)
    b.start(ready_timeout=20)
    yield b
    b.stop()


def test_backend_serves_health_and_launcher_ui(backend):
    with urllib.request.urlopen(f"{backend.url}/api/health", timeout=5) as resp:
        health = json.loads(resp.read())
    assert health["status"] == "ok"

    with urllib.request.urlopen(f"{backend.url}/", timeout=5) as resp:
        html = resp.read().decode("utf-8")
    assert "AYT 启动器" in html  # 启动器自己的静态目录被显式托管（override 生效）

    with urllib.request.urlopen(f"{backend.url}/api/datasets", timeout=5) as resp:
        datasets = json.loads(resp.read())
    assert "datasets" in datasets


def test_backend_stop_is_graceful(backend):
    thread = backend._thread
    backend.stop()
    assert thread is not None and not thread.is_alive()


def test_port_file_written(tmp_path):
    b = LauncherBackend(base_dir=tmp_path, frontend_dist=STATIC_DIR, start_queue_runner=False)
    b.start(ready_timeout=20)
    try:
        assert b.port_file is not None
        assert b.port_file.read_text(encoding="utf-8").strip() == str(b.port)
    finally:
        b.stop()


@pytest.mark.skipif(sys.platform != "win32", reason="单实例锁是 Win32 互斥体")
def test_single_instance_second_acquire_detected():
    name = f"Local\\AYT-Launcher-Test-{time.time_ns()}"
    first, handle = launcher_app.acquire_single_instance(name)
    assert first is False and handle
    second, _ = launcher_app.acquire_single_instance(name)
    assert second is True


@pytest.mark.skipif(sys.platform != "win32", reason="窗口探测只在 Windows")
def test_focus_existing_window_absent_returns_false():
    assert launcher_app.focus_existing_window("不存在的窗口-4f2a") is False


def test_static_ui_bundle_complete():
    """启动器静态包完整性：index 引用 live.js/favicon，字体随包。"""
    index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    assert 'src="live.js"' in index
    assert 'href="favicon.svg"' in index
    live = (STATIC_DIR / "live.js").read_text(encoding="utf-8")
    assert "window.__live = LIVE" in live and "/api/health" in live
    woff2 = list((STATIC_DIR / "fonts").rglob("*.woff2"))
    assert len(woff2) >= 300, f"字体缺失：{len(woff2)}"


def test_env_report_endpoint(backend, tmp_path):
    """环境自检端点：轻量采样（python/平台/gpu/磁盘/工作目录）。"""
    with urllib.request.urlopen(f"{backend.url}/api/launcher/env-report", timeout=10) as resp:
        env = json.loads(resp.read())
    assert env["python"] and env["platform"]
    assert "gpu" in env and set(env["gpu"]) == {"name", "memory", "driver"}
    assert "disks" in env
    assert Path(env["base_dir"]) == tmp_path.resolve()
