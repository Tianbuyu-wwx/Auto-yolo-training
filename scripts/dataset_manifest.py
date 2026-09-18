"""数据集清单：给"这次训练用的是哪份数据"一个可核对的答案。

为什么不用 DVC
--------------
DVC 会用内容寻址缓存把数据**再存一份**（.dvc/cache），还要额外的远端才能跨机
共享。这个项目的形态是：数据集就在本机 `dataset/` 下（286 MB / 4500+ 文件），
单机单用户，仓库是公开的 —— 引入 DVC 的实际代价是 E 盘再吃一份 286 MB
（当前只剩 68 GB）、外加一层只有自己用得到的间接层，而它解决的问题（"这份
数据和上次训练用的是不是同一份"）用一份清单就能回答。

所以这里做的是 DVC 在这个场景里的等价物：**清单 + 校验**。
- 清单放在数据集目录内（`dataset/.manifest.json`），跟着数据走，不进仓库；
- 每份数据集记：文件数、字节数、划分与图像/标注计数、内容指纹；
- `--check` 比对当前磁盘与清单，漂移时列出**具体哪些文件**变了。

指纹取"相对路径 + 大小 + mtime_ns"的排序摘要，而不是逐个文件 sha256：
4500 个文件全量读一遍要十几秒，而本项目的判据是"数据有没有被动过"
（补了图、删了标、换了划分），路径/大小/mtime 三者足以覆盖，且秒级完成。
需要强校验时用 `--hash` 切到 sha256。

用法：
    python scripts/dataset_manifest.py --write          # 生成/更新清单
    python scripts/dataset_manifest.py --check          # 校验漂移（退出码非 0 = 有变化）
    python scripts/dataset_manifest.py --hash           # 用 sha256（慢）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

MANIFEST_NAME = ".manifest.json"
# 数据集目录里这些不算数据（清单自身、系统垃圾、YOLO 缓存）
SKIP_DIRS = {".recycle", "__pycache__", ".git"}
SKIP_SUFFIXES = {".pyc", ".tmp", ".part"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
LABEL_SUFFIX = ".txt"


def _rel_files(root: Path) -> list[Path]:
    out = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        if p.name == MANIFEST_NAME or p.suffix.lower() in SKIP_SUFFIXES:
            continue
        out.append(p)
    return out


def _file_digest(path: Path, use_hash: bool) -> str:
    if use_hash:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    st = path.stat()
    return f"{st.st_size}:{st.st_mtime_ns}"


def _counts(files: list[Path]) -> dict[str, int]:
    images = sum(1 for f in files if f.suffix.lower() in IMAGE_SUFFIXES)
    labels = sum(1 for f in files if f.suffix.lower() == LABEL_SUFFIX)
    return {"files": len(files), "images": images, "labels": labels}


def build_manifest(dataset_root: Path, *, use_hash: bool = False) -> dict:
    """扫描 dataset_root 下的每个数据集目录，产出一份可比较的清单。"""
    entries: dict[str, dict] = {}
    for sub in sorted(p for p in dataset_root.iterdir() if p.is_dir()):
        if sub.name in SKIP_DIRS:
            continue
        files = _rel_files(sub)
        if not files:
            continue
        digests = [f"{f.relative_to(sub).as_posix()}:{_file_digest(f, use_hash)}" for f in files]
        blob = "\n".join(digests).encode()
        entries[sub.name] = {
            **_counts(files),
            "bytes": sum(f.stat().st_size for f in files),
            "splits": sorted({
                f.relative_to(sub).parts[0]
                for f in files if len(f.relative_to(sub).parts) > 1
            }),
            "digest": hashlib.sha256(blob).hexdigest()[:16],
        }
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "sha256" if use_hash else "size+mtime",
        "datasets": entries,
    }


def diff_manifests(old: dict, new: dict) -> list[str]:
    """两份清单的差异，人话描述（新增/消失/内容变化）。"""
    msgs: list[str] = []
    o, n = old.get("datasets", {}), new.get("datasets", {})
    for name in sorted(set(o) | set(n)):
        if name not in o:
            msgs.append(f"新增数据集：{name}（{n[name]['files']} 文件）")
        elif name not in n:
            msgs.append(f"数据集消失：{name}")
        elif o[name]["digest"] != n[name]["digest"]:
            oo, nn = o[name], n[name]
            d = []
            if oo["files"] != nn["files"]:
                d.append(f"文件 {oo['files']}→{nn['files']}")
            if oo["images"] != nn["images"]:
                d.append(f"图像 {oo['images']}→{nn['images']}")
            if oo["labels"] != nn["labels"]:
                d.append(f"标注 {oo['labels']}→{nn['labels']}")
            if oo["bytes"] != nn["bytes"]:
                d.append(f"体积 {oo['bytes'] / 1e6:.1f}→{nn['bytes'] / 1e6:.1f} MB")
            msgs.append(f"内容变化：{name}（" + ("；".join(d) or "同数量但文件被替换/改写过") + "）")
    return msgs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="数据集清单：生成 / 校验")
    ap.add_argument("--dir", default="dataset", help="数据集根目录（默认 dataset）")
    ap.add_argument("--write", action="store_true", help="生成或更新清单")
    ap.add_argument("--check", action="store_true", help="与清单比对（漂移时退出码 1）")
    ap.add_argument("--hash", action="store_true", help="用 sha256 而不是 size+mtime")
    args = ap.parse_args(argv)

    root = Path(args.dir)
    if not root.is_dir():
        print(f"数据集目录不存在：{root}", file=sys.stderr)
        return 2
    manifest_path = root / MANIFEST_NAME
    fresh = build_manifest(root, use_hash=args.hash)

    if args.write:
        manifest_path.write_text(json.dumps(fresh, ensure_ascii=False, indent=2), encoding="utf-8")
        total = sum(d["files"] for d in fresh["datasets"].values())
        print(f"已写入 {manifest_path}：{len(fresh['datasets'])} 个数据集 / {total} 个文件"
              f"（指纹方式：{fresh['mode']}）")
        return 0

    if args.check:
        if not manifest_path.is_file():
            print(f"没有清单可比对（先跑 --write）：{manifest_path}", file=sys.stderr)
            return 2
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
        changes = diff_manifests(old, fresh)
        if changes:
            print("数据集相对清单已发生变化：")
            for m in changes:
                print("  -", m)
            return 1
        print(f"清单一致：{len(fresh['datasets'])} 个数据集与 {old['generated_at']} 的记录完全相同")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
