#!/usr/bin/env python
"""核对 ModelRegistry 里每条版本记录的权重是否还在磁盘上（死链接扫描）。

为什么需要它：``copy_model=False``（默认）注册的版本只记录路径，而 ``runs/`` 下的
训练产物会被滚动保留清理 —— 记录还在、权重没了。注册表本身不会报错，测试也不会
变红，``get_production_model()`` 更无从察觉，只能靠显式扫描把它揪出来。

用法：
    python scripts/check_registry_weights.py                  # 只报告
    python scripts/check_registry_weights.py --delete-dead    # 顺手清掉死记录（只动注册表）

退出码：0 = 无死链接（或已清理干净）；1 = 仍有死链接。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.model_registry import ModelRegistry


def main() -> int:
    parser = argparse.ArgumentParser(description="扫描注册表里的权重死链接")
    parser.add_argument("--base-dir", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument(
        "--delete-dead",
        action="store_true",
        help="删除权重已丢失的注册记录（只动 versions.json，不动 runs/ 下的任何文件）",
    )
    args = parser.parse_args()

    registry = ModelRegistry(args.base_dir)
    rows: list[tuple[str, str, str, bool]] = []
    for dataset, versions in sorted(registry.list_all().items()):
        for item in versions:
            rows.append(
                (
                    dataset,
                    item["version_id"],
                    item.get("status", ""),
                    ModelRegistry.weights_available(item.get("model_path")),
                )
            )

    if not rows:
        print("注册表为空，无死链接。")
        return 0

    width = max(len(r[1]) for r in rows)
    for dataset, version_id, status, ok in rows:
        print(f"  [{'OK     ' if ok else 'MISSING'}] {dataset:<18} {version_id:<{width}}  {status}")

    dead = [r for r in rows if not r[3]]
    print(f"\n共 {len(rows)} 条版本，权重缺失 {len(dead)} 条")

    if dead and args.delete_dead:
        for dataset, version_id, _status, _ok in dead:
            registry.delete_version(dataset, version_id)
            print(f"  已删除死记录: {dataset}/{version_id}")
        print(f"共删除 {len(dead)} 条")
        return 0

    if dead:
        print("提示：这些版本仍会出现在控制台（已标注「权重已丢失」）；")
        print("      用 --delete-dead 可把记录清掉（runs/ 下的文件不会被碰）。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
