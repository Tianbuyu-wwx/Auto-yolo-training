"""打包 AYT-Setup.exe（PyInstaller，onefile + windowed）。

用法：
    python installer/build_setup.py            # 构建
    python installer/build_setup.py --clean    # 先清理旧产物再构建

产物：installer/dist/AYT-Setup.exe（自包含单文件：双击 → 安装向导）
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ENTRY = HERE / "entry_setup.py"
ICON = HERE / "assets" / "ayt.ico"


def ensure_icon() -> None:
    """没有图标就现场画一个（圆角蓝底 + 白色播放箭头）。"""
    if ICON.exists():
        return
    from PIL import Image, ImageDraw

    ICON.parent.mkdir(parents=True, exist_ok=True)
    base = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(base)
    d.rounded_rectangle((6, 6, 250, 250), radius=54, fill=(37, 99, 235, 255))
    d.rounded_rectangle((52, 96, 204, 160), radius=16, fill=(255, 255, 255, 240))
    d.polygon([(122, 106), (122, 150), (158, 128)], fill=(37, 99, 235, 255))
    base.save(
        ICON,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print("icon ->", ICON)


def main() -> int:
    ap = argparse.ArgumentParser(description="打包 AYT-Setup.exe")
    ap.add_argument("--clean", action="store_true", help="构建前清理 build/dist")
    args = ap.parse_args()

    if args.clean:
        for d in (HERE / "build", HERE / "dist"):
            shutil.rmtree(d, ignore_errors=True)

    ensure_icon()

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        "AYT-Setup",
        "--icon",
        str(ICON),
        "--distpath",
        str(HERE / "dist"),
        "--workpath",
        str(HERE / "build"),
        "--specpath",
        str(HERE / "build"),
        "--paths",
        str(ROOT),
        "--hidden-import",
        "installer.ayt_setup.gui",
        "--hidden-import",
        "installer.ayt_setup.execute",
        str(ENTRY),
    ]
    print(" ".join(cmd), "\n")
    proc = subprocess.run(cmd, cwd=str(ROOT))
    if proc.returncode != 0:
        return proc.returncode

    out = HERE / "dist" / "AYT-Setup.exe"
    if out.exists():
        print(f"\n产物：{out}（{out.stat().st_size / 1e6:.1f} MB）")
    else:
        print("\n警告：构建结束但未找到产物")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
