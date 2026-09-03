"""
数据集验证入口脚本
独立运行数据验证，检查数据集质量
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import argparse
import json

from src.branding import get_cli_banner
from src.data_validator import validate_dataset


def main():
    parser = argparse.ArgumentParser(
        description="YOLO数据集验证工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 验证指定数据集
  python validate_data.py cabel-damage-mini

  # 验证并输出详细JSON报告
  python validate_data.py cabel-damage-mini --json
        """
    )

    parser.add_argument(
        "dataset_name",
        help="数据集子目录名称（位于 dataset/ 下）"
    )

    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="输出JSON格式报告"
    )

    args = parser.parse_args()

    base_dir = Path(__file__).parent
    dataset_path = base_dir / "dataset" / args.dataset_name

    if not dataset_path.exists():
        print(f"错误: 数据集不存在: {dataset_path}")
        sys.exit(1)

    print(get_cli_banner())
    print(f"正在验证数据集: {args.dataset_name}")
    print(f"路径: {dataset_path}")
    print("-" * 50)

    report = validate_dataset(str(dataset_path))

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(f"验证结果: {'通过' if report.is_valid else '未通过'}")
        print(f"错误数: {len(report.get_errors())}")
        print(f"警告数: {len(report.get_warnings())}")
        print("-" * 50)

        if report.stats:
            print("统计信息:")
            for split, stats in report.stats.get("splits", {}).items():
                if stats.get("images", 0) > 0:
                    print(f"  [{split}] 图像: {stats['images']}, 标注: {stats['labels']}, 目标框: {stats['bounding_boxes']}")
                    if stats.get("class_distribution"):
                        print(f"    类别分布: {stats['class_distribution']}")

        if report.get_errors():
            print("-" * 50)
            print("错误详情:")
            for issue in report.get_errors()[:10]:
                print(f"  [ERROR][{issue.category}] {issue.message}")
                if issue.file_path:
                    print(f"    文件: {issue.file_path}")

        if report.get_warnings():
            print("-" * 50)
            print("警告详情:")
            for issue in report.get_warnings()[:10]:
                print(f"  [WARN][{issue.category}] {issue.message}")

    sys.exit(0 if report.is_valid else 1)


if __name__ == "__main__":
    main()
