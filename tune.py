"""
YOLO超参数自动搜索入口脚本
基于Optuna自动寻找最优训练超参数
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import argparse

from src.branding import get_cli_banner
from src.config_generator import ConfigGenerator
from src.hyperparameter_tuning import SearchSpace, YOLOHyperparameterTuner


def build_search_space_from_args(args) -> SearchSpace:
    """根据命令行参数构建搜索空间"""
    space = SearchSpace()

    # 模型选择
    if args.models:
        space.model_candidates = args.models.split(",")

    # 图像尺寸范围
    if args.imgsz_range:
        parts = args.imgsz_range.split(",")
        space.imgsz_min = int(parts[0])
        space.imgsz_max = int(parts[1]) if len(parts) > 1 else space.imgsz_min
        space.imgsz_step = int(parts[2]) if len(parts) > 2 else 640

    # 批次大小范围
    if args.batch_range:
        parts = args.batch_range.split(",")
        space.batch_min = int(parts[0])
        space.batch_max = int(parts[1]) if len(parts) > 1 else space.batch_min
        space.batch_step = int(parts[2]) if len(parts) > 2 else 4

    # 学习率范围
    if args.lr_range:
        parts = args.lr_range.split(",")
        space.lr0_min = float(parts[0])
        space.lr0_max = float(parts[1]) if len(parts) > 1 else space.lr0_min

    # 优化器
    if args.optimizers:
        space.optimizer_candidates = args.optimizers.split(",")

    # 固定参数
    fixed = {}
    if args.fix_epochs:
        fixed["epochs"] = args.fix_epochs
    if args.fix_device:
        fixed["device"] = args.fix_device
    space.fixed_params = fixed

    return space


def main():
    parser = argparse.ArgumentParser(
        description="YOLO超参数自动搜索工具（基于Optuna）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基础用法：对数据集进行超参搜索
  python tune.py cabel-damage-mini

  # 指定搜索轮数和优化指标
  python tune.py cabel-damage-mini --n-trials 30 --metric metrics/mAP50-95(B)

  # 自定义搜索空间
  python tune.py cabel-damage-mini --models yolov8s.pt,yolov8m.pt --imgsz-range 640,1280,640

  # 限制批次大小范围
  python tune.py cabel-damage-mini --batch-range 4,16,4 --lr-range 1e-4,1e-2

  # 使用完整流水线（验证+搜索+训练）
  python tune.py cabel-damage-mini --full-pipeline --epochs 150
        """
    )

    # 数据集名称
    parser.add_argument(
        "dataset_name",
        help="数据集子目录名称（位于 dataset/ 下）"
    )

    # 搜索配置
    parser.add_argument(
        "--n-trials", "-n",
        type=int,
        default=20,
        help="搜索轮数 (默认: 20)"
    )

    parser.add_argument(
        "--metric", "-m",
        default="metrics/mAP50(B)",
        help="优化指标 (默认: metrics/mAP50(B))"
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="超时时间（秒）"
    )

    parser.add_argument(
        "--study-name",
        default=None,
        help="Optuna study名称"
    )

    # 搜索空间配置
    parser.add_argument(
        "--models",
        default="yolov8s.pt,yolov8m.pt",
        help="候选模型，逗号分隔 (默认: yolov8s.pt,yolov8m.pt)"
    )

    parser.add_argument(
        "--imgsz-range",
        default="640,1280,640",
        help="图像尺寸范围 min,max,step (默认: 640,1280,640)"
    )

    parser.add_argument(
        "--batch-range",
        default="4,16,4",
        help="批次大小范围 min,max,step (默认: 4,16,4)"
    )

    parser.add_argument(
        "--lr-range",
        default="1e-4,1e-2",
        help="学习率范围 min,max (默认: 1e-4,1e-2)"
    )

    parser.add_argument(
        "--optimizers",
        default="AdamW,SGD,NAdam,RAdam",
        help="候选优化器，逗号分隔 (默认: AdamW,SGD,NAdam,RAdam)"
    )

    # 固定参数
    parser.add_argument(
        "--fix-epochs",
        type=int,
        default=30,
        help="搜索时固定训练轮数 (默认: 30)"
    )

    parser.add_argument(
        "--fix-device",
        default="0",
        help="固定GPU设备 (默认: 0)"
    )

    # 完整流水线模式
    parser.add_argument(
        "--full-pipeline",
        action="store_true",
        help="执行完整流水线：验证 -> 搜索 -> 使用最优参数训练"
    )

    parser.add_argument(
        "--epochs",
        type=int,
        default=150,
        help="完整流水线模式下的训练轮数 (默认: 150)"
    )

    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="跳过数据验证"
    )

    args = parser.parse_args()

    base_dir = Path(__file__).parent
    dataset_path = base_dir / "dataset" / args.dataset_name

    if not dataset_path.exists():
        print(f"错误: 数据集不存在: {dataset_path}")
        sys.exit(1)

    # 生成或定位data.yaml
    config_generator = ConfigGenerator(str(base_dir))
    data_yaml_path = config_generator.generate_data_yaml(args.dataset_name)

    print(get_cli_banner())
    print("=" * 70)
    print(f"数据集: {args.dataset_name}")
    print(f"数据配置: {data_yaml_path}")
    print(f"搜索轮数: {args.n_trials}")
    print(f"优化指标: {args.metric}")
    print(f"搜索时训练轮数: {args.fix_epochs}")
    if args.timeout:
        print(f"超时限制: {args.timeout}秒")
    print("-" * 70)

    # 构建搜索空间
    search_space = build_search_space_from_args(args)
    print("搜索空间:")
    print(f"  模型: {search_space.model_candidates}")
    print(f"  图像尺寸: {search_space.imgsz_min}-{search_space.imgsz_max} (步长{search_space.imgsz_step})")
    print(f"  批次: {search_space.batch_min}-{search_space.batch_max} (步长{search_space.batch_step})")
    print(f"  学习率: {search_space.lr0_min}-{search_space.lr0_max}")
    print(f"  优化器: {search_space.optimizer_candidates}")
    print("=" * 70)

    # 创建调优器
    tuner = YOLOHyperparameterTuner(
        data_yaml_path=data_yaml_path,
        base_dir=str(base_dir),
        study_name=args.study_name or f"{args.dataset_name}_tuning",
    )

    # 执行搜索
    result = tuner.tune(
        n_trials=args.n_trials,
        search_space=search_space,
        metric=args.metric,
        timeout=args.timeout,
    )

    print("=" * 70)
    print("搜索完成!")
    print(f"  最优值 ({args.metric}): {result.best_value:.4f}")
    print(f"  搜索轮数: {result.n_trials}")
    print(f"  总耗时: {result.duration:.2f}秒")
    print("-" * 70)
    print("最优参数:")
    for key, value in result.best_params.items():
        print(f"  {key}: {value}")
    print("=" * 70)

    # 保存结果路径
    tuning_dir = base_dir / "tuning"
    print(f"\n搜索结果已保存到: {tuning_dir}")

    # 完整流水线模式：使用最优参数执行完整训练
    if args.full_pipeline:
        print("\n" + "=" * 70)
        print("进入完整训练模式（使用最优参数）")
        print("=" * 70)

        from src.training_pipeline import TrainingPipeline

        pipeline = TrainingPipeline(str(base_dir))

        # 构建训练覆盖参数
        overrides = result.best_params.copy()
        overrides["epochs"] = args.epochs

        report = pipeline.run(
            dataset_name=args.dataset_name,
            skip_validation=args.skip_validation,
            training_overrides=overrides,
        )

        print("=" * 70)
        print(f"完整流水线结果: {'成功' if report.success else '失败'}")
        print(f"总耗时: {report.total_duration:.2f}秒")
        for stage in report.stages:
            status = "[PASS]" if stage["success"] else "[FAIL]"
            print(f"  {status} {stage['stage']}: {stage['message']}")
        print("=" * 70)

    sys.exit(0)


if __name__ == "__main__":
    main()
