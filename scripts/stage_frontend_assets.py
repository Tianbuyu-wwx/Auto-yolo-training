#!/usr/bin/env python
"""把前端产物装填到 ``src/api/static/``（打包 wheel 前必须执行）。

为什么需要它：控制台是 FastAPI 托管的一堆静态文件，而它们生成在仓库根目录的
``frontend/dist`` —— 不在任何 Python 包里。不做这一步，``pip install`` 出来的
wheel 只有 API，首页退回 JSON 提示（``ayt-web`` 装出来是个没有界面的控制台）。

用法::

    python scripts/stage_frontend_assets.py            # 装填 + 报告
    python scripts/stage_frontend_assets.py --check    # 只校验是否已是最新（CI 用）
"""
from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT_ROOT / "frontend" / "dist"
TARGET = PROJECT_ROOT / "src" / "api" / "static"


def _display(path: Path) -> str:
    """打印用路径：项目内显示相对路径，项目外（测试/外部 target）原样显示"""
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def _tree_diff(a: Path, b: Path) -> list[str]:
    """列出两棵树的差异（只比较文件名与内容，够用且不引第三方依赖）"""
    diffs: list[str] = []
    files_a = {p.relative_to(a).as_posix() for p in a.rglob("*") if p.is_file()}
    files_b = {p.relative_to(b).as_posix() for p in b.rglob("*") if p.is_file()}
    diffs += [f"仅存在于 dist: {f}" for f in sorted(files_a - files_b)]
    diffs += [f"仅存在于 static: {f}" for f in sorted(files_b - files_a)]
    for rel in sorted(files_a & files_b):
        if not filecmp.cmp(a / rel, b / rel, shallow=False):
            diffs.append(f"内容不同: {rel}")
    return diffs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="装填前端产物到 src/api/static/")
    parser.add_argument("--check", action="store_true", help="只校验，不写盘（不一致则退出码 1）")
    args = parser.parse_args(argv)

    if not (SOURCE / "index.html").is_file():
        print(f"[stage] 找不到前端产物：{SOURCE}\n"
              f"        先构建：cd frontend && pnpm install && pnpm build", file=sys.stderr)
        return 2

    if args.check:
        if not TARGET.exists():
            print(f"[stage] {_display(TARGET)} 不存在：需要跑一次装填", file=sys.stderr)
            return 1
        diffs = _tree_diff(SOURCE, TARGET)
        if diffs:
            print("[stage] 包内静态资源与前端产物不一致：", file=sys.stderr)
            for line in diffs[:20]:
                print(f"        {line}", file=sys.stderr)
            return 1
        print("[stage] 包内静态资源与 frontend/dist 一致")
        return 0

    if TARGET.exists():
        shutil.rmtree(TARGET)
    shutil.copytree(SOURCE, TARGET)
    count = sum(1 for _ in TARGET.rglob("*") if _.is_file())
    size_mb = sum(p.stat().st_size for p in TARGET.rglob("*") if p.is_file()) / 1024 ** 2
    print(f"[stage] {_display(SOURCE)} → {_display(TARGET)}"
          f"（{count} 个文件，{size_mb:.2f} MB）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
