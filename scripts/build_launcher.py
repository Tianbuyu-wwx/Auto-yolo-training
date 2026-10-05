"""打包桌面启动器为单文件 AYT.exe（PyInstaller，onefile + windowed）。

用法：
    python scripts/build_launcher.py            # 构建
    python scripts/build_launcher.py --clean    # 先清理旧产物再构建

产物：**项目根目录下的 AYT.exe** —— 双击打开启动器；exe 在项目根，
运行时能直接定位项目（训练/推理子进程用本机 Python 跑项目代码）。
"""

from __future__ import annotations

import argparse
import contextlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "src" / "launcher" / "__main__.py"
STATIC = ROOT / "src" / "launcher" / "static"

# 明确排除的重型依赖：启动器主进程链不 import 它们
# （训练/推理是子进程，用本机 Python 跑项目代码，不依赖 exe 内的包）
# 注意：cv2 **不能排**——数据校验（src/data_validator.py）在主进程内跑，需要它；
# torch/ultralytics 可以排——只有训练/推理子进程才用。
EXCLUDES = [
    "torch",
    "torchvision",
    "ultralytics",
    "matplotlib",
    "pandas",
    "scipy",
    "gradio",
    "IPython",
    "notebook",
]


def main() -> int:
    ap = argparse.ArgumentParser(description="打包 AYT.exe（桌面启动器，产物落项目根）")
    ap.add_argument("--clean", action="store_true", help="构建前清理 build/launcher 与旧 AYT.exe")
    args = ap.parse_args()

    work_dir = ROOT / "build" / "launcher"
    out_exe = ROOT / "AYT.exe"
    if args.clean:
        shutil.rmtree(work_dir, ignore_errors=True)
        with contextlib.suppress(OSError):
            out_exe.unlink()  # 正在运行时会被占用，留给 PyInstaller 给出明确报错

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        "AYT",
        "--distpath",
        str(ROOT),  # 产物直接落项目根（双击即用）
        "--workpath",
        str(work_dir),
        "--specpath",
        str(work_dir),
        "--paths",
        str(ROOT),
        "--add-data",
        f"{STATIC};src/launcher/static",
        "--hidden-import",
        "src.api.admin",
        "--hidden-import",
        "src.launcher.backend",
        "--hidden-import",
        "src.launcher.features",
        "--hidden-import",
        "src.runtime_env",
    ]
    for mod in EXCLUDES:
        cmd += ["--exclude-module", mod]
    cmd.append(str(ENTRY))

    print(" ".join(cmd), "\n")
    proc = subprocess.run(cmd, cwd=str(ROOT))
    if proc.returncode != 0:
        return proc.returncode

    if out_exe.exists():
        print(f"\n产物：{out_exe}（{out_exe.stat().st_size / 1e6:.1f} MB）—— 双击即启动器")
    else:
        print("\n警告：构建结束但未找到产物")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
