"""
模型评估入口脚本
对训练好的模型进行测试集评估
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import argparse

from src.branding import get_cli_banner
from src.evaluator import ModelEvaluator


def main():
    parser = argparse.ArgumentParser(
        description="YOLO模型评估工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 评估指定模型
  python eval.py runs/detect/cabel-damage-mini_auto/weights/best.pt data_cabel-damage-mini.yaml

  # 评估训练运行目录中的最佳模型
  python eval.py --run runs/detect/cabel-damage-mini_auto --data data_cabel-damage-mini.yaml

  # 指定评估参数
  python eval.py model.pt data.yaml --imgsz 1280 --batch 8 --conf 0.25
        """
    )

    parser.add_argument(
        "model",
        nargs="?",
        help="模型文件路径 (.pt)"
    )

    parser.add_argument(
        "data",
        nargs="?",
        help="data.yaml路径"
    )

    parser.add_argument(
        "--run", "-r",
        help="训练运行目录（自动查找weights/best.pt）"
    )

    parser.add_argument(
        "--dataset", "-d",
        default="unknown",
        help="数据集名称"
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
        "--conf",
        type=float,
        default=0.001,
        help="置信度阈值 (默认: 0.001)"
    )

    parser.add_argument(
        "--iou",
        type=float,
        default=0.6,
        help="IoU阈值 (默认: 0.6)"
    )

    parser.add_argument(
        "--compare",
        help="与历史报告目录对比"
    )

    args = parser.parse_args()

    # 确定模型路径
    if args.run:
        run_dir = Path(args.run)
        model_path = run_dir / "weights" / "best.pt"
        if not model_path.exists():
            print(f"错误: 未找到最佳模型: {model_path}")
            sys.exit(1)
        # 自动推断数据集名称
        if args.dataset == "unknown":
            args.dataset = run_dir.name.replace("_auto", "").replace("_eval", "")
    elif args.model:
        model_path = Path(args.model)
    else:
        print("错误: 请指定模型路径或训练运行目录")
        parser.print_help()
        sys.exit(1)

    # 确定data.yaml路径
    if args.data:
        data_yaml = args.data
    else:
        # 尝试自动查找
        base_dir = Path(__file__).parent
        dataset_name = args.dataset
        # 优先查找 configs/models/ 目录
        auto_yaml = base_dir / "configs" / "models" / f"data_{dataset_name}.yaml"
        if auto_yaml.exists():
            data_yaml = str(auto_yaml)
        else:
            # 回退到旧路径（兼容）
            auto_yaml = base_dir / f"data_{dataset_name}.yaml"
            if auto_yaml.exists():
                data_yaml = str(auto_yaml)
            else:
                print("错误: 请指定data.yaml路径")
                sys.exit(1)

    print(get_cli_banner())
    print("=" * 60)
    print(f"模型: {model_path}")
    print(f"数据: {data_yaml}")
    print(f"数据集: {args.dataset}")
    print(f"图像尺寸: {args.imgsz}")
    print(f"批次: {args.batch}")
    print("=" * 60)

    evaluator = ModelEvaluator()

    report = evaluator.evaluate(
        model_path=str(model_path),
        data_yaml=data_yaml,
        dataset_name=args.dataset,
        imgsz=args.imgsz,
        batch=args.batch,
        conf=args.conf,
        iou=args.iou,
        compare_with=args.compare,
    )

    print("\n评估结果:")
    print("-" * 60)
    print(f"  mAP@50:     {report.metrics.mAP50:.4f}")
    print(f"  mAP@50-95:  {report.metrics.mAP50_95:.4f}")
    print(f"  Precision:  {report.metrics.precision:.4f}")
    print(f"  Recall:     {report.metrics.recall:.4f}")
    print(f"  Fitness:    {report.metrics.fitness:.4f}")

    if report.metrics.class_metrics:
        print("\n各类别指标:")
        for name, metrics in report.metrics.class_metrics.items():
            ap50 = metrics.get('AP50', 0)
            ap5095 = metrics.get('AP50_95', 0)
            print(f"  {name:15s} AP50={ap50:.4f}  AP50-95={ap5095:.4f}")

    if report.comparison:
        print("\n历史对比:")
        print(f"  历史最佳: {report.comparison['best_historical_mAP50']:.4f}")
        print(f"  当前结果: {report.comparison['current_mAP50']:.4f}")
        improvement = report.comparison['improvement']
        symbol = "↑" if improvement > 0 else "↓"
        print(f"  变化: {symbol} {abs(improvement):.4f}")

    print("=" * 60)
    print("评估完成!")


if __name__ == "__main__":
    main()
