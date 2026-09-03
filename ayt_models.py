"""
模型清单与下载 CLI（阶段 C5）

``ayt-models`` 命令：
    - 列出所有支持的预训练模型（75 个）
    - 按条件过滤（task/family/size）
    - 检查本地 basemodels/ 已下载哪些
    - 下载指定模型到 basemodels/

用法：
    python ayt_models.py list [--task detect] [--family yolov8] [--size n]
    python ayt_models.py local
    python ayt_models.py download yolov8n.pt
    python ayt_models.py download yolo26m-cls.pt
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.branding import get_cli_banner
from src.model_catalog import (
    list_available_models,
    local_models,
)
from src.model_downloader import ensure_model, is_model_downloaded
from src.task_types import TaskType, get_task_spec


def _parse_task(value: str) -> TaskType:
    return get_task_spec(value).task


def cmd_list(args: argparse.Namespace) -> int:
    """列出支持的模型清单（按条件过滤）。"""
    models = list_available_models(
        task=_parse_task(args.task) if args.task else None,
        family=args.family,
        size=args.size,
    )
    if not models:
        print("没有匹配的模型")
        return 1

    # 按 family → size → task 分组
    by_family: dict[str, list] = {}
    for m in models:
        by_family.setdefault(m.family, []).append(m)
    for family in sorted(by_family):
        print(f"\n[{family}]")
        for m in by_family[family]:
            tag = "✓" if is_model_downloaded(m.filename, Path.cwd()) else " "
            print(f"  [{tag}] {m.filename:<32s} {m.display_name}")
    return 0


def cmd_local(args: argparse.Namespace) -> int:
    """列出已下载到 basemodels/ 的模型。"""
    models = local_models(Path.cwd())
    if not models:
        print("basemodels/ 目录无预训练模型")
        return 1
    for m in models:
        path = Path.cwd() / "basemodels" / m.filename
        size_mb = path.stat().st_size / (1024 * 1024) if path.exists() else 0
        print(f"  {m.filename:<32s} {size_mb:>8.1f} MB  {m.display_name}")
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    """下载指定模型到 basemodels/。"""
    filename = args.filename
    if not filename.endswith(".pt"):
        filename = filename + ".pt"
    try:
        path = ensure_model(filename, Path.cwd())
    except FileNotFoundError as e:
        print(f"下载失败: {e}")
        return 1
    size_mb = path.stat().st_size / (1024 * 1024) if path.exists() else 0
    print(f"✓ 已就绪: {path} ({size_mb:.1f} MB)")
    return 0


def main() -> int:
    print(get_cli_banner())
    print()

    parser = argparse.ArgumentParser(
        description="YOLO 预训练模型清单与下载工具（阶段 C5）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 列出全部 75 个支持的预训练模型
  python ayt_models.py list

  # 仅列出 detect 任务、yolov8 family、size=n 的模型
  python ayt_models.py list --task detect --family yolov8 --size n

  # 列出已下载的模型
  python ayt_models.py local

  # 下载指定模型
  python ayt_models.py download yolov8n.pt
  python ayt_models.py download yolo26m-cls
""",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = subparsers.add_parser("list", help="列出支持的预训练模型")
    p_list.add_argument("--task", choices=["detect", "segment", "pose", "classify", "obb"])
    p_list.add_argument("--family", choices=["yolov5", "yolov8", "yolov11", "yolo26"])
    p_list.add_argument("--size", choices=["n", "s", "m", "l", "x"])
    p_list.set_defaults(func=cmd_list)

    # local
    p_local = subparsers.add_parser("local", help="列出已下载的预训练模型")
    p_local.set_defaults(func=cmd_local)

    # download
    p_dl = subparsers.add_parser("download", help="下载预训练模型到 basemodels/")
    p_dl.add_argument("filename", help="模型文件名（如 yolov8n.pt 或 yolo26m-cls）")
    p_dl.set_defaults(func=cmd_download)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
