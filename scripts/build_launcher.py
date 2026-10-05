"""打包桌面启动器为单文件 AYT.exe（PyInstaller，onefile + windowed）。

用法：
    python scripts/build_launcher.py            # 构建
    python scripts/build_launcher.py --clean    # 先清理旧产物再构建

产物：dist/launcher/AYT.exe —— 双击打开启动器（训练/推理子进程用本机 Python）。
"""

from __future__ import annotations

import argparse
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
    ap = argparse.ArgumentParser(description="打包 AYT.exe（桌面启动器）")
    ap.add_argument("--clean", action="store_true", help="构建前清理 build/dist")
    args = ap.parse_args()

    out_dir = ROOT / "dist" / "launcher"
    work_dir = ROOT / "build" / "launcher"
    if args.clean:
        for d in (out_dir, work_dir):
            shutil.rmtree(d, ignore_errors=True)

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
        str(out_dir),
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

    out = out_dir / "AYT.exe"
    if out.exists():
        print(f"\n产物：{out}（{out.stat().st_size / 1e6:.1f} MB）")
    else:
        print("\n警告：构建结束但未找到产物")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
