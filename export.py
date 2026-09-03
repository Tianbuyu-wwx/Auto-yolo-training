"""
模型导出入口脚本
将训练好的模型导出为多种部署格式
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import argparse

from src.branding import get_cli_banner
from src.model_exporter import ModelExporter


def main():
    parser = argparse.ArgumentParser(
        description="YOLO模型导出工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 导出指定模型
  python export.py runs/detect/cabel-damage-mini_auto/weights/best.pt

  # 导出训练运行目录中的最佳模型
  python export.py --run runs/detect/cabel-damage-mini_auto

  # 导出指定格式
  python export.py model.pt --formats onnx,engine,openvino

  # FP16半精度导出
  python export.py model.pt --half

  # 列出支持的格式
  python export.py --list
        """
    )

    parser.add_argument(
        "model",
        nargs="?",
        help="模型文件路径 (.pt)"
    )

    parser.add_argument(
        "--run", "-r",
        help="训练运行目录（自动查找weights/best.pt）"
    )

    parser.add_argument(
        "--formats", "-f",
        default="onnx,engine",
        help="导出格式，逗号分隔 (默认: onnx,engine)"
    )

    parser.add_argument(
        "--imgsz", "-s",
        type=int,
        default=640,
        help="输入图像尺寸 (默认: 640)"
    )

    parser.add_argument(
        "--half",
        action="store_true",
        help="使用FP16半精度"
    )

    parser.add_argument(
        "--int8",
        action="store_true",
        help="使用INT8量化"
    )

    parser.add_argument(
        "--dynamic",
        action="store_true",
        default=True,
        help="ONNX动态轴 (默认: True)"
    )

    parser.add_argument(
        "--simplify",
        action="store_true",
        default=True,
        help="简化ONNX模型 (默认: True)"
    )

    parser.add_argument(
        "--opset",
        type=int,
        default=12,
        help="ONNX opset版本 (默认: 12)"
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="列出支持的导出格式"
    )

    args = parser.parse_args()

    exporter = ModelExporter()

    # 列出支持的格式
    if args.list:
        print("支持的导出格式:")
        print("-" * 60)
        for info in exporter.list_supported_formats():
            status = "[Y]" if info.get("supported") else "[N]"
            dep = info.get("dependency", "")
            print(f"  {status} {info['format']:12s} - {info['description']}")
            if dep:
                print(f"      依赖: {dep}")
        print("-" * 60)
        sys.exit(0)

    # 确定模型路径
    if args.run:
        run_dir = Path(args.run)
        model_path = run_dir / "weights" / "best.pt"
        if not model_path.exists():
            print(f"错误: 未找到最佳模型: {model_path}")
            sys.exit(1)
    elif args.model:
        model_path = Path(args.model)
        if not model_path.exists():
            print(f"错误: 模型文件不存在: {model_path}")
            sys.exit(1)
    else:
        print("错误: 请指定模型路径或训练运行目录")
        parser.print_help()
        sys.exit(1)

    formats = args.formats.split(",")

    print(get_cli_banner())
    print("=" * 60)
    print(f"模型: {model_path}")
    print(f"格式: {formats}")
    print(f"图像尺寸: {args.imgsz}")
    print(f"FP16: {args.half}")
    print(f"INT8: {args.int8}")
    print("=" * 60)

    report = exporter.export(
        model_path=str(model_path),
        formats=formats,
        imgsz=args.imgsz,
        half=args.half,
        int8=args.int8,
        dynamic=args.dynamic,
        simplify=args.simplify,
        opset=args.opset,
    )

    print("\n导出结果:")
    print("-" * 60)
    for result in report.results:
        status = "✓" if result.success else "✗"
        size = f"({result.file_size_mb:.2f} MB)" if result.file_size > 0 else ""
        print(f"  {status} {result.format:12s} {size}")
        if result.output_path:
            print(f"      输出: {result.output_path}")
        if not result.success:
            print(f"      错误: {result.message}")

    print("-" * 60)
    print(f"成功: {report.success_count}/{report.total_count}")
    print("=" * 60)

    if report.success_count == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
