"""AYT 安装器 · 执行器：把安装计划变成真实动作。

设计：
  - ``*_cmd`` 系列是纯函数（命令构造，可单测，无副作用）；
  - ``run_command`` 是唯一的进程执行点（逐行回调，供 CLI / GUI 消费）；
  - ``build_actions`` 把「扫描报告 + 用户选项」翻译成动作序列；
  - ``run_actions`` 顺序执行动作并汇报每步结果（dry-run 只展示不执行）。
"""

from __future__ import annotations

import platform
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# ---------------- 常量 ----------------

PYTORCH_CU128_INDEX = "https://download.pytorch.org/whl/cu128"
PYTORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"
TUNA_INDEX = "https://pypi.tuna.tsinghua.edu.cn/simple"

AYT_SPEC = "auto-yolo-training[launcher]"

LineCB = Callable[[str], None] | None


def _no_window() -> int:
    if platform.system() == "Windows":
        return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return 0


# ---------------- 命令构造（纯函数） ----------------


def venv_create_cmd(python_exe: str, venv_dir: Path) -> list[str]:
    return [python_exe, "-m", "venv", str(venv_dir)]


def pip_cmd(venv_python: str, *args: str) -> list[str]:
    return [venv_python, "-m", "pip", "install", "--no-input", *args]


def pip_upgrade_cmd(venv_python: str) -> list[str]:
    return pip_cmd(venv_python, "--upgrade", "pip", "setuptools", "wheel")


def torch_install_cmd(venv_python: str, gpu: bool) -> list[str]:
    index = PYTORCH_CU128_INDEX if gpu else PYTORCH_CPU_INDEX
    return pip_cmd(venv_python, "--index-url", index, "torch", "torchvision")


def ayt_install_cmd(venv_python: str, source: str, mirror: bool) -> list[str]:
    args: list[str] = []
    if mirror:
        args += ["--index-url", TUNA_INDEX]
    args.append(source or AYT_SPEC)
    return pip_cmd(venv_python, *args)


def venv_python_path(install_dir: Path) -> str:
    """安装目录内 venv 的解释器路径（Windows 布局）。"""
    return str(Path(install_dir) / "venv" / "Scripts" / "python.exe")


def shortcut_target(install_dir: Path) -> str:
    """快捷方式指向的启动器入口（venv 里的 ayt-launcher）。"""
    return str(Path(install_dir) / "venv" / "Scripts" / "ayt-launcher.exe")


# ---------------- 进程执行 ----------------


@dataclass
class ActionResult:
    ok: bool
    exit_code: int | None = None
    detail: str = ""


def run_command(
    cmd: list[str],
    on_line: LineCB = None,
    cwd: Path | None = None,
    timeout: float | None = None,
) -> ActionResult:
    """跑命令并逐行回调输出（stdout+stderr 合并）。"""
    try:
        proc = subprocess.Popen(  # noqa: S603 —— 安装器本就是干这个的
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(cwd) if cwd else None,
            creationflags=_no_window(),
        )
    except OSError as exc:
        return ActionResult(False, None, str(exc))

    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            if on_line:
                on_line(line.rstrip())
        rc = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        return ActionResult(False, None, "timeout")
    return ActionResult(rc == 0, rc, f"exit={rc}")


def create_desktop_shortcut(install_dir: Path, on_line: LineCB = None) -> ActionResult:
    """用 PowerShell 创建桌面快捷方式（无 pywin32 依赖）。"""
    target = shortcut_target(install_dir)
    ps = (
        "$ws = New-Object -ComObject WScript.Shell; "
        "$desktop = [Environment]::GetFolderPath('Desktop'); "
        f"$s = $ws.CreateShortcut((Join-Path $desktop 'AYT 启动器.lnk')); "
        f"$s.TargetPath = '{target}'; "
        f"$s.WorkingDirectory = '{install_dir}'; "
        "$s.Save(); Write-Output 'shortcut-created'"
    )
    return run_command(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], on_line=on_line)


# ---------------- 选项与动作编排 ----------------


@dataclass
class InstallOptions:
    install_dir: Path
    mode: str = "venv"  # "venv"（隔离安装，推荐）| "reuse"（复用现有环境，跳过安装）
    gpu: bool = True  # True → 装 cu128 版 torch（机器确有 GPU 时）
    mirror: bool = False  # 依赖下载走清华镜像
    ayt_source: str = ""  # AYT 本体来源：wheel 路径 | pip spec；空 = PyPI
    make_shortcut: bool = True


def build_actions(rep: dict, opt: InstallOptions) -> list[dict]:
    """把「扫描报告 + 用户选项」翻译成动作序列。

    每项：{id, title, kind: 'cmd'|'call', cmd?, call?, note}
    """
    actions: list[dict] = []

    # 1) 定位 Python 3.12（M2 假定已有；无则动作标注为不可行）
    interps = rep.get("interpreters") or []
    p312 = [i for i in interps if (i.get("version") or "").startswith("3.12")]
    base_python = p312[0]["path"] if p312 else None

    venv_dir = Path(opt.install_dir) / "venv"
    venv_py = venv_python_path(opt.install_dir)
    venv_present = bool((rep.get("install") or {}).get("venv_present"))

    if opt.mode == "reuse":
        reuse_py = rep.get("selected_python") or base_python
        actions.append(
            {
                "id": "reuse",
                "title": "复用现有环境",
                "kind": "call",
                "call": "noop",
                "note": f"跳过安装，使用 {reuse_py}",
            }
        )
        if opt.make_shortcut:
            actions.append(
                {
                    "id": "shortcut",
                    "title": "创建桌面快捷方式（指向现有环境的 ayt-launcher）",
                    "kind": "call",
                    "call": "shortcut",
                    "note": "桌面",
                }
            )
        return actions

    # 隔离安装
    if not base_python:
        actions.append(
            {
                "id": "python",
                "title": "Python 3.12",
                "kind": "call",
                "call": "noop",
                "note": "未找到 3.12 解释器 —— 自动下载 embeddable 将在 M3 提供；请先安装 Python 3.12",
            }
        )
        return actions

    if not venv_present:
        actions.append(
            {
                "id": "venv",
                "title": "创建虚拟环境",
                "kind": "cmd",
                "cmd": venv_create_cmd(base_python, venv_dir),
                "note": str(venv_dir),
            }
        )
    if not venv_present or not _all_deps_ok(rep):
        actions.append(
            {"id": "pip", "title": "升级 pip / setuptools / wheel", "kind": "cmd", "cmd": pip_upgrade_cmd(venv_py)}
        )
        is_gpu = bool(opt.gpu and (rep.get("gpu") or {}).get("present"))
        actions.append(
            {
                "id": "torch",
                "title": f"安装 PyTorch（{'CUDA 12.8' if is_gpu else 'CPU'} 版）",
                "kind": "cmd",
                "cmd": torch_install_cmd(venv_py, is_gpu),
            }
        )
        actions.append(
            {
                "id": "ayt",
                "title": "安装 AYT（含桌面启动器）",
                "kind": "cmd",
                "cmd": ayt_install_cmd(venv_py, opt.ayt_source, opt.mirror),
                "note": opt.ayt_source or AYT_SPEC,
            }
        )
    if opt.make_shortcut:
        actions.append(
            {"id": "shortcut", "title": "创建桌面快捷方式", "kind": "call", "call": "shortcut", "note": "桌面"}
        )
    return actions


def _all_deps_ok(rep: dict) -> bool:
    """既有 venv 且依赖全满足（venv 内的 packages 报告缺省即视为未满足）。"""
    install = rep.get("install") or {}
    if not install.get("venv_present"):
        return False
    pkgs = rep.get("packages") or {}
    from .scan import REQUIRED_PACKAGES, satisfies

    return all(satisfies(pkgs.get(n), m) for n, m in REQUIRED_PACKAGES.items())


def run_actions(
    actions: list[dict],
    install_dir: Path,
    on_line: LineCB = None,
    on_step: Callable[[int, dict], None] | None = None,
    dry_run: bool = False,
) -> list[dict]:
    """顺序执行动作；失败即停（返回含每步结果的列表）。"""
    results: list[dict] = []
    for i, act in enumerate(actions):
        if on_step:
            on_step(i, act)
        if dry_run:
            results.append({**act, "ok": True, "dry_run": True})
            continue

        if act["kind"] == "cmd":
            res = run_command(act["cmd"], on_line=on_line)
        elif act.get("call") == "shortcut":
            res = create_desktop_shortcut(install_dir, on_line=on_line)
        else:  # noop
            res = ActionResult(True, 0, act.get("note", ""))
        results.append({**act, "ok": res.ok, "detail": res.detail})
        if not res.ok:
            break
    return results
