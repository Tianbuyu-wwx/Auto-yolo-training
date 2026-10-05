"""Frozen（PyInstaller）运行时的路径与解释器解析。

开发态（``python -m src.launcher``）一切照旧：
  - ``project_root()`` = 仓库根（本文件的上上级）；
  - ``worker_python_cmd()`` = ``[sys.executable]``。

打包态（AYT.exe）：
  - 主进程跑在 PyInstaller 的 ``_MEIPASS`` 里（代码 + static 都在 exe 内）；
  - 训练/推理子进程需要「**稳定的项目路径 + 本机 Python（带训练依赖）**」——
    ``_MEIPASS`` 会随主进程退出被删除，且 exe 自身不能当解释器，
    所以子进程必须落在真实项目目录、用真实 Python 启动。

项目根探测顺序（frozen）：环境变量 ``AYT_PROJECT_ROOT`` → exe 目录（或其上级 3 层）
→ 当前工作目录（或其上级 3 层）。

解释器探测：``AYT_PYTHON`` → 项目内 ``venv``/``.venv`` → ``py -3.12`` →
``C:/Python312`` → ``%LOCALAPPDATA%`` 下的 Python 3.12/3.13 → PATH 上的
``python``/``py``。**每个候选都会实测能否 import torch**——PATH 上先命中的
往往是无关环境的 Python（如工具链自带的 3.14），不检查会以「训练子进程秒退」
收场。全部落选返回 ``None``，由调用方给出可操作的报错。
"""

from __future__ import annotations

import functools
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

_MARKER = ("pyproject.toml", "src/launcher")


def is_frozen() -> bool:
    """是否运行在 PyInstaller 打包产物里。"""
    return bool(getattr(sys, "frozen", False))


def _looks_like_project(path: Path) -> bool:
    return (path / _MARKER[0]).is_file() and (path / _MARKER[1]).is_dir()


def _search_upward(start: Path, levels: int = 3) -> Path | None:
    cur = start.resolve()
    for _ in range(levels):
        if _looks_like_project(cur):
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def project_root() -> Path:
    """子进程使用的稳定项目根目录。"""
    if not is_frozen():
        return Path(__file__).resolve().parents[1]

    env = os.environ.get("AYT_PROJECT_ROOT")
    if env:
        cand = Path(env).expanduser()
        if _looks_like_project(cand):
            return cand.resolve()

    exe_dir = Path(sys.executable).resolve().parent
    found = _search_upward(exe_dir)
    if found is not None:
        return found

    found = _search_upward(Path.cwd())
    if found is not None:
        return found

    raise RuntimeError(
        "未找到 AYT 项目目录：请把 AYT.exe 放进项目文件夹（或上级），"
        "或设置环境变量 AYT_PROJECT_ROOT 指向项目根。"
    )


def no_window_flags() -> int:
    """Windows：``CREATE_NO_WINDOW`` 创建标志。

    GUI（无 console）进程 spawn console 子进程（python / nvidia-smi / …）时，
    不传这个标志系统会为每个子进程**弹出一个新的控制台窗口**——打包成
    windowed exe 后表现为「命令行窗口持续弹出」。非 Windows 返回 0。
    """
    if platform.system() == "Windows":
        return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return 0


def _can_import_torch(py_cmd: list[str]) -> bool:
    """实测候选解释器能否 import torch（find_spec，不真加载）。"""
    try:
        proc = subprocess.run(
            [
                *py_cmd,
                "-c",
                "import importlib.util as u; raise SystemExit(0 if u.find_spec('torch') else 1)",
            ],
            capture_output=True,
            timeout=20,
            creationflags=no_window_flags(),
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _candidates() -> list[list[str]]:
    """候选解释器（命令前缀列表），按「最可能装了训练依赖」排序。"""
    out: list[list[str]] = []

    env = os.environ.get("AYT_PYTHON")
    if env and Path(env).is_file():
        out.append([env])

    try:
        root: Path | None = project_root()
    except RuntimeError:
        root = None
    if root is not None:
        for rel in ("venv/Scripts/python.exe", ".venv/Scripts/python.exe"):
            cand = root / rel
            if cand.is_file():
                out.append([str(cand)])

    if shutil.which("py"):
        out.append(["py", "-3.12"])

    local = os.environ.get("LOCALAPPDATA") or ""
    for fixed in (
        Path("C:/Python312/python.exe"),
        Path(local) / "Programs/Python/Python312/python.exe",
        Path(local) / "Programs/Python/Python313/python.exe",
    ):
        if fixed.is_file():
            out.append([str(fixed)])

    me = Path(sys.executable).resolve()
    for name in ("python", "python3"):
        which = shutil.which(name)
        if which and Path(which).resolve() != me:
            out.append([which])
    if shutil.which("py"):
        out.append(["py"])

    return out


@functools.lru_cache(maxsize=1)
def worker_python_cmd() -> list[str] | None:
    """可执行 ``-m src.xxx`` 且**能 import torch** 的子进程解释器命令前缀。

    frozen 下逐个实测候选（结果缓存），全部落选返回 ``None``；
    开发态恒为当前解释器（不检查——开发环境的依赖由开发者自理）。
    """
    if not is_frozen():
        return [sys.executable]

    for cand in _candidates():
        if _can_import_torch(cand):
            return cand
    return None
