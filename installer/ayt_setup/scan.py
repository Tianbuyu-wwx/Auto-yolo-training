"""AYT 安装器 · 本机环境扫描（只读，无副作用）。

设计：
  - 每个检查项是独立函数，返回可 JSON 序列化的 dict；
  - 子进程全部带超时与 CREATE_NO_WINDOW（不弹黑窗）；
  - Windows 专有检测（注册表 / nvidia-smi）异常时优雅降级；
  - ``scan()`` 聚合出报告 dict，``plan.py`` 消费它生成「缺什么补什么」的计划。
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

DEFAULT_INSTALL_DIR_NAME = "AYT"

# 关键依赖与最低版本（与 pyproject / requirements 对齐）
REQUIRED_PACKAGES: dict[str, str] = {
    "torch": "2.0",
    "torchvision": "0.15",
    "ultralytics": "8.0",
    "fastapi": "0.100",
    "uvicorn": "0.20",
    "pywebview": "6.2",
    "pydantic": "2.0",
    "pydantic-settings": "2.0",
    "numpy": "1.26",
}

# 网络可达性目标
NET_TARGETS: dict[str, str] = {
    "pypi": "https://pypi.org/simple/",
    "tuna": "https://pypi.tuna.tsinghua.edu.cn/simple/",
    "pytorch_cu128": "https://download.pytorch.org/whl/cu128/",
}

# WebView2 Runtime 的 EdgeUpdate 注册表 GUID（微软官方检测法）
WEBVIEW2_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"

MIN_DISK_GB_GPU = 8.0
MIN_DISK_GB_CPU = 4.0


# ---------------- 基础工具 ----------------


def _no_window() -> int:
    if platform.system() == "Windows":
        return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return 0


def _run(args: list[str], timeout: float = 15.0) -> tuple[int | None, str, str]:
    """跑子进程；返回 (returncode|None, stdout, stderr)。None = 未能启动/超时。"""
    try:
        p = subprocess.run(  # noqa: S603 —— 本安装器就是干这个的
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=_no_window(),
        )
        return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return None, "", "timeout"
    except OSError as exc:
        return None, "", str(exc)


def _ver_tuple(text: str | None) -> tuple[int, int] | None:
    if not text:
        return None
    m = re.match(r"(\d+)\.(\d+)", text.strip())
    return (int(m.group(1)), int(m.group(2))) if m else None


def satisfies(version: str | None, minimum: str) -> bool:
    """version >= minimum（按 major.minor 比较；版本不可解析视为不满足）。"""
    a, b = _ver_tuple(version), _ver_tuple(minimum)
    return bool(a and b and a >= b)


def default_install_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("USERPROFILE") or "~"
    return Path(base).expanduser() / DEFAULT_INSTALL_DIR_NAME


# ---------------- 检查项 ----------------


def find_interpreters(install_dir: Path) -> list[dict]:
    """找候选 Python 解释器。返回 [{path, version, source}]（含 AYT venv，若有）。"""
    found: list[dict] = []
    seen: set[str] = set()

    def probe(path: str, source: str) -> None:
        key = os.path.normcase(os.path.abspath(path))
        if key in seen:
            return
        seen.add(key)
        rc, out, _ = _run(
            [path, "-c", "import sys; print('%d.%d.%d' % sys.version_info[:3])"]
        )
        if rc == 0 and out:
            found.append({"path": path, "version": out, "source": source})

    # AYT venv（之前装过的话）
    venv_py = install_dir / "venv" / "Scripts" / "python.exe"
    if venv_py.is_file():
        probe(str(venv_py), "AYT venv")

    # py launcher（Windows 标准发现方式）
    rc, out, _ = _run(["py", "-3.12", "-c", "import sys; print(sys.executable)"])
    if rc == 0 and out:
        probe(out, "py launcher")

    # PATH
    for name in ("python3.12", "python"):
        exe = shutil.which(name)
        if exe:
            probe(exe, "PATH")

    # 常见安装位置
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    for cand in (
        local / "Programs" / "Python" / "Python312" / "python.exe",
        Path("C:/Python312/python.exe"),
        Path("C:/Program Files/Python312/python.exe"),
    ):
        if cand.is_file():
            probe(str(cand), "common path")

    return found


def probe_packages(python_exe: str) -> dict:
    """在一个子进程里批量查关键包版本（importlib.metadata，不 import 重库）。"""
    code = (
        "import json, importlib.metadata as m\n"
        "names = " + json.dumps(list(REQUIRED_PACKAGES)) + "\n"
        "out = {}\n"
        "for n in names:\n"
        "    try:\n"
        "        out[n] = m.version(n)\n"
        "    except Exception:\n"
        "        out[n] = None\n"
        "print(json.dumps(out))\n"
    )
    rc, out, _ = _run([python_exe, "-c", code], timeout=30)
    if rc == 0 and out:
        try:
            return json.loads(out.splitlines()[-1])
        except json.JSONDecodeError:
            pass
    return dict.fromkeys(REQUIRED_PACKAGES)


def probe_torch_cuda(python_exe: str) -> dict:
    """查 torch 版本与 CUDA 支持（会初始化 CUDA，留给 60s 超时）。"""
    code = (
        "import json\n"
        "try:\n"
        "    import torch\n"
        "    print(json.dumps({'installed': True, 'version': torch.__version__,\n"
        "                      'cuda': torch.version.cuda,\n"
        "                      'available': bool(torch.cuda.is_available())}))\n"
        "except Exception as e:\n"
        "    print(json.dumps({'installed': False, 'error': str(e)[:120]}))\n"
    )
    rc, out, _ = _run([python_exe, "-c", code], timeout=60)
    if rc == 0 and out:
        try:
            return json.loads(out.splitlines()[-1])
        except json.JSONDecodeError:
            pass
    return {"installed": False, "error": (out or "probe failed")[:120]}


def probe_gpu() -> dict:
    """NVIDIA 显卡与驱动（nvidia-smi）。"""
    exe = shutil.which("nvidia-smi") or "nvidia-smi"
    rc, out, err = _run(
        [exe, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
        timeout=15,
    )
    if rc == 0 and out:
        gpus = []
        for line in out.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                gpus.append({"name": parts[0], "memory": parts[1], "driver": parts[2]})
        if gpus:
            return {"present": True, "gpus": gpus}
    return {"present": False, "error": (err or "nvidia-smi not found")[:120]}


def probe_webview2() -> dict:
    """WebView2 Runtime —— 标准注册表检测，目录兜底。"""
    try:
        import winreg  # type: ignore[import-not-found]

        for root, path in (
            (
                winreg.HKEY_LOCAL_MACHINE,
                rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_GUID}",
            ),
            (
                winreg.HKEY_LOCAL_MACHINE,
                rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_GUID}",
            ),
            (
                winreg.HKEY_CURRENT_USER,
                rf"Software\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_GUID}",
            ),
        ):
            try:
                with winreg.OpenKey(root, path) as key:
                    version, _ = winreg.QueryValueEx(key, "pv")
                    return {"present": True, "version": str(version), "source": "registry"}
            except OSError:
                continue
    except ImportError:
        pass

    for base in ("PROGRAMFILES(X86)", "PROGRAMFILES"):
        d = Path(os.environ.get(base, "")) / "Microsoft" / "EdgeWebView" / "Application"
        if d.is_dir():
            return {"present": True, "version": "unknown", "source": str(d)}
    return {"present": False}


def probe_disk(path: Path) -> dict:
    target = path if path.exists() else Path(path.anchor or "C:/")
    try:
        usage = shutil.disk_usage(str(target))
        return {
            "path": str(target),
            "free_gb": round(usage.free / 1024**3, 1),
            "total_gb": round(usage.total / 1024**3, 1),
        }
    except OSError as exc:
        return {"path": str(target), "error": str(exc)[:120]}


def probe_network(timeout: float = 4.0) -> dict:
    """PyPI / 镜像可达性（HEAD 请求）。"""
    result: dict[str, dict] = {}
    for name, url in NET_TARGETS.items():
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "AYT-Setup"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 —— 固定 https
                result[name] = {"ok": True, "status": resp.status}
        except Exception as exc:  # noqa: BLE001 —— 网络探测全量兜底
            result[name] = {"ok": False, "error": str(exc)[:100]}
    return result


def probe_install_state(install_dir: Path) -> dict:
    """既往 AYT 安装状态（venv / 启动器入口）。"""
    venv_py = install_dir / "venv" / "Scripts" / "python.exe"
    launcher_exe = install_dir / "venv" / "Scripts" / "ayt-launcher.exe"
    return {
        "install_dir": str(install_dir),
        "dir_exists": install_dir.is_dir(),
        "venv_present": venv_py.is_file(),
        "venv_python": str(venv_py) if venv_py.is_file() else None,
        "launcher_present": launcher_exe.is_file(),
    }


# ---------------- 聚合 ----------------


def scan(install_dir: str | Path | None = None) -> dict:
    """完整本机环境扫描（只读）。返回可 JSON 序列化的报告。"""
    t0 = time.time()
    install = Path(install_dir) if install_dir else default_install_dir()

    rep: dict = {
        "schema": 1,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "runner_python": sys.version.split()[0],
        "install_dir": str(install),
    }

    rep["interpreters"] = find_interpreters(install)
    rep["gpu"] = probe_gpu()
    rep["webview2"] = probe_webview2()
    rep["disk"] = probe_disk(install)
    rep["network"] = probe_network()
    rep["install"] = probe_install_state(install)

    # 选定解释器：优先 3.12 中「来源优先级」最高者（venv > py launcher > PATH > 常见路径）
    def _rank(item: dict) -> int:
        order = ["AYT venv", "py launcher", "PATH", "common path"]
        return order.index(item["source"]) if item["source"] in order else len(order)

    p312 = [i for i in rep["interpreters"] if (i.get("version") or "").startswith("3.12")]
    selected = None
    if p312:
        selected = sorted(p312, key=_rank)[0]["path"]
    elif rep["interpreters"]:
        selected = rep["interpreters"][0]["path"]
    rep["selected_python"] = selected

    if selected:
        rep["packages"] = probe_packages(selected)
        rep["torch_cuda"] = probe_torch_cuda(selected)

    rep["elapsed_s"] = round(time.time() - t0, 1)
    return rep
