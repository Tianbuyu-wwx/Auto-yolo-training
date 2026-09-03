"""
YOLO模型自动训练入口脚本
一键执行数据验证、配置生成、模型训练的完整流程
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import argparse

from src.branding import get_cli_banner
from src.training_pipeline import run_training


def main():
    parser = argparse.ArgumentParser(
        description="YOLO模型自动训练工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基础用法：使用数据集名称自动训练
  python train.py cabel-damage-mini

  # 指定模型和超参数
  python train.py cabel-damage-mini --model yolov8m.pt --imgsz 1280 --batch 6 --epochs 200

  # 跳过数据验证（已知数据正常时）
  python train.py cabel-damage-mini --skip-validation

  # 覆盖训练参数
  python train.py cabel-damage-mini --override lr0=0.0005 dropout=0.1
        """
    )

    parser.add_argument(
        "dataset_name",
        help="数据集子目录名称（位于 dataset/ 下）"
    )

    parser.add_argument(
        "--model", "-m",
        default="yolov8s.pt",
        help="预训练模型 (默认: yolov8s.pt)"
    )

    parser.add_argument(
        "--imgsz", "-s",
        type=int,
        default=640,
        help="输入图像尺寸 (默认: 640)"
    )

    parser.add_argument(
        "--batch", "-b",
        type=int,
        default=16,
        help="批次大小 (默认: 16)"
    )

    parser.add_argument(
        "--epochs", "-e",
        type=int,
        default=150,
        help="训练轮数 (默认: 150)"
    )

    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="跳过数据验证阶段"
    )

    parser.add_argument(
        "--override",
        nargs="*",
        default=[],
        help="覆盖训练参数，格式: key=value"
    )

    args = parser.parse_args()

    # 解析覆盖参数
    overrides = {}
    for item in args.override:
        if "=" in item:
            key, value = item.split("=", 1)
            # 尝试类型转换
            try:
                value = int(value)
            except ValueError:
                try:
                    value = float(value)
                except ValueError:
                    if value.lower() == "true":
                        value = True
                    elif value.lower() == "false":
                        value = False
            overrides[key] = value

    print(get_cli_banner())
    print("=" * 60)
    print(f"数据集: {args.dataset_name}")
    print(f"模型: {args.model}")
    print(f"图像尺寸: {args.imgsz}")
    print(f"批次: {args.batch}")
    print(f"轮数: {args.epochs}")
    if overrides:
        print(f"参数覆盖: {overrides}")
    print("=" * 60)

    # 执行训练流水线
    report = run_training(
        dataset_name=args.dataset_name,
        model=args.model,
        imgsz=args.imgsz,
        batch=args.batch,
        epochs=args.epochs,
        skip_validation=args.skip_validation,
        training_overrides=overrides,
    )

    print("=" * 60)
    print(f"执行结果: {'成功' if report.success else '失败'}")
    print(f"总耗时: {report.total_duration:.2f}秒")
    print("-" * 60)
    print("阶段详情:")
    for stage in report.stages:
        status = "[PASS]" if stage["success"] else "[FAIL]"
        print(f"  {status} {stage['stage']}: {stage['message']} ({stage['duration']:.2f}s)")
    print("=" * 60)

    if not report.success:
        sys.exit(1)


if __name__ == "__main__":
    main()
