"""启动器扩展能力：推理服务进程管理 / 受控打开路径 / 诊断包。

设计约束（launcher-plan §2）：
- 推理服务是**独立子进程**（uvicorn）——崩溃不连坐启动器、可被 kill、
  不吃主进程内存；启动/停止/状态统一由本模块治理。
- 路径操作一律白名单 + ``resolve()`` 校验，拒绝目录穿越。
- 模型自动发现 = ``runs/detect/*/weights/best.pt`` 里最新的那个。
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# 允许「打开」（资源管理器/默认程序）的白名单目录（相对 base_dir）
OPENABLE_DIRS = ("artifacts/logs", "artifacts/runs", "dataset", "artifacts/exports", "artifacts/reports")


class InferenceManager:
    """推理服务子进程生命周期。``start()`` 阻塞到 ``/health`` 可用（或超时）。"""

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir).resolve()
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self.port: int | None = None
        self._model: str | None = None

    # ---------------- 内部 ----------------
    @property
    def _log_file(self) -> Path:
        return self.base_dir / "artifacts" / "logs" / "inference.log"

    def _alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _discover_model(self) -> str | None:
        """自动发现推理模型：runs/detect/*/weights/best.pt 里最新的那个。"""
        try:
            cands = sorted(
                (self.base_dir / "artifacts" / "runs" / "detect").glob("*/weights/best.pt"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            cands = []
        return str(cands[0]) if cands else None

    @staticmethod
    def _port_free(port: int) -> bool:
        import socket

        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return True
            except OSError:
                return False

    def _wait_health(self, port: int, timeout: float = 20.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._proc is not None and self._proc.poll() is not None:
                return False  # 子进程已死（模型加载失败等）
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as r:
                    if r.status == 200:
                        return True
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(0.4)
        return False

    # ---------------- 对外 ----------------
    def status(self) -> dict:
        alive = self._alive()
        return {
            "running": alive,
            "pid": self._proc.pid if (alive and self._proc) else None,
            "port": self.port if alive else None,
            "url": f"http://127.0.0.1:{self.port}" if (alive and self.port) else None,
            "model": self._model if alive else None,
        }

    def start(self, model_path: str | None = None, port: int = 8000) -> dict:
        with self._lock:
            if self._alive():
                return {"status": "already_running", **self.status()}
            model = model_path or self._discover_model()
            if not model:
                return {"status": "error", "message": "没有可用模型（runs/detect/*/weights/best.pt 为空）"}
            from src.launcher.backend import pick_free_port
            from src.runtime_env import no_window_flags, project_root, worker_python_cmd

            try:
                root = project_root()
                py = worker_python_cmd()
            except RuntimeError as exc:
                return {"status": "error", "message": str(exc)}
            if py is None:
                return {"status": "error", "message": "未找到可用的本机 Python（推理子进程需要）"}

            if not self._port_free(port):
                port = pick_free_port()
            (self.base_dir / "artifacts" / "logs").mkdir(parents=True, exist_ok=True)
            log = open(self._log_file, "a", encoding="utf-8")  # noqa: SIM115 —— 交给子进程持有
            env = dict(os.environ)
            env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
            try:
                self._proc = subprocess.Popen(
                    [*py, "-m", "src.inference_service", "--model", model, "--port", str(port)],
                    cwd=str(root),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    env=env,
                    creationflags=no_window_flags(),
                )
            except OSError as exc:
                return {"status": "error", "message": f"拉起推理子进程失败：{exc}"}
            self.port = port
            self._model = model
            if not self._wait_health(port, timeout=25.0):
                self.stop()
                return {"status": "error", "message": "推理服务启动超时（见 logs/inference.log）"}
            return {"status": "started", "model": model, **self.status()}

    def stop(self, timeout: float = 8.0) -> dict:
        with self._lock:
            if not self._alive():
                return {"status": "not_running", **self.status()}
            assert self._proc is not None
            self._proc.terminate()
            try:
                self._proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=3)
            # 未提交的 log 句柄由 Popen 持有；进程死后系统回收
            self._proc = None
            return {"status": "stopped"}


# ==================== 受控打开 ====================


def open_path(rel_path: str, base_dir: str | Path) -> dict:
    """在资源管理器/默认程序中打开白名单内的目录或文件。

    白名单：``logs/ runs/ dataset/ exports/ reports/``（相对 base_dir）。
    resolve 后必须仍位于白名单目录内，否则拒绝（防目录穿越）。
    """
    base = Path(base_dir).resolve()
    raw = str(rel_path or "").strip().replace("\\", "/").lstrip("/")
    if not raw:
        return {"status": "error", "message": "path 不能为空"}
    target = (base / raw).resolve()
    allowed_root = None
    for name in OPENABLE_DIRS:
        root = (base / name).resolve()
        try:
            target.relative_to(root)
            allowed_root = root
            break
        except ValueError:
            continue
    if allowed_root is None:
        return {"status": "error", "message": f"仅允许打开：{'/'.join(OPENABLE_DIRS)} 之下"}
    if not target.exists():
        # 目录不存在时尝试创建（logs/reports 常见为空）
        if target.suffix == "":
            target.mkdir(parents=True, exist_ok=True)
        else:
            return {"status": "error", "message": f"不存在：{raw}"}
    try:
        os.startfile(str(target))  # noqa: S606 —— 受控白名单，非注入面
    except OSError as exc:
        return {"status": "error", "message": f"打开失败：{exc}"}
    return {"status": "ok", "opened": str(target)}


# ==================== 诊断包 ====================


def diag_pack(base_dir: str | Path) -> dict:
    """打包诊断信息：logs + 端口文件 + 环境报告 + 运行/注册表快照 → reports/diag-<ts>.zip。"""
    import json

    base = Path(base_dir).resolve()
    reports = base / "artifacts" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = reports / f"diag-{ts}.zip"

    def _collect_env() -> dict:
        env: dict = {}
        try:
            from importlib import metadata

            for pkg in ("torch", "ultralytics", "fastapi", "uvicorn"):
                try:
                    env[pkg] = metadata.version(pkg)
                except Exception:  # noqa: BLE001
                    env[pkg] = None
        except Exception:  # noqa: BLE001
            pass
        env["python"] = sys.version.split()[0]
        env["platform"] = sys.platform
        return env

    counts = {"logs": 0, "misc": 0}
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        # logs/（全部文本类）
        logs_dir = base / "artifacts" / "logs"
        if logs_dir.is_dir():
            for f in sorted(logs_dir.glob("*.*")):
                if f.suffix.lower() in (".log", ".txt", ".out"):
                    z.write(f, f"logs/{f.name}")
                    counts["logs"] += 1
        # 环境与快照
        z.writestr("env-report.json", json.dumps(_collect_env(), ensure_ascii=False, indent=1))
        runs = sorted((base / "artifacts" / "runs" / "detect").glob("*")) if (base / "artifacts" / "runs" / "detect").is_dir() else []
        z.writestr(
            "runs-snapshot.json",
            json.dumps([p.name for p in runs if p.is_dir()], ensure_ascii=False, indent=1),
        )
        reg_dir = base / "registry"
        if reg_dir.is_dir():
            for f in sorted(reg_dir.glob("*.json")):
                z.write(f, f"registry/{f.name}")
                counts["misc"] += 1
    return {"status": "ok", "file": str(out), "bytes": out.stat().st_size, **counts}


# ==================== 数据集 ZIP 上传 ====================


def upload_zip(zip_path: str, api_base: str, name: str = "", overwrite: bool = False) -> dict:
    """把本地 zip 上传到 ``/api/datasets/upload``（urllib 手工 multipart）。

    供 ``LauncherWinAPI.upload_zip`` 使用：WebView 里没有浏览器 form 通道，
    python 侧代传最直接（也是本机回环，不经过网络栈外发）。
    """
    path = Path(zip_path)
    if not path.is_file():
        return {"status": "error", "message": f"文件不存在：{zip_path}"}
    boundary = "----AYTLauncher" + uuid.uuid4().hex
    zdata = path.read_bytes()

    def _field(field_name: str, value: str) -> bytes:
        return (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{field_name}"\r\n\r\n{value}\r\n'
        ).encode()

    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
        "Content-Type: application/zip\r\n\r\n"
    ).encode() + zdata + b"\r\n"
    body += _field("name", name or path.stem)
    body += _field("overwrite", "true" if overwrite else "false")
    body += f"--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        api_base.rstrip("/") + "/api/datasets/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:  # noqa: S310 —— 本机回环
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = ""
        with contextlib.suppress(Exception):
            detail = json.loads(exc.read()).get("detail", "")
        return {"status": "error", "message": detail or f"HTTP {exc.code}"}
    except (OSError, urllib.error.URLError) as exc:
        return {"status": "error", "message": f"上传失败：{exc}"}
