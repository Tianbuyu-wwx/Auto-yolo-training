"""
自动数据集管理器
负责扫描、检测、转换和管理所有数据集格式
"""

import logging
import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from src.convert_classification_to_yolo import convert_classification_to_yolo
from src.dataset_scanner import DatasetProfile, DatasetScanner

logger = logging.getLogger(__name__)


class DatasetFormat(Enum):
    """数据集格式类型"""
    YOLO = "yolo"                           # 标准YOLO格式（可直接训练）
    CLASSIFICATION = "classification"       # 图像分类格式（需要转换）
    UNKNOWN = "unknown"                     # 无法识别


@dataclass
class DatasetStatus:
    """数据集状态信息"""
    name: str
    path: Path
    format: DatasetFormat
    is_ready: bool                          # 是否可以直接用于训练
    needs_conversion: bool                  # 是否需要转换
    image_count: int = 0
    label_count: int = 0
    classes: list[str] = None
    issues: list[str] = None
    conversion_info: dict | None = None  # 转换相关信息

    def __post_init__(self):
        if self.classes is None:
            self.classes = []
        if self.issues is None:
            self.issues = []


class AutoDatasetManager:
    """自动数据集管理器"""

    def __init__(self, dataset_base_dir: str):
        self.dataset_base_dir = Path(dataset_base_dir).resolve()
        self.dataset_base_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("数据集管理器初始化: %s", self.dataset_base_dir)

    def scan_all_datasets(self) -> list[DatasetStatus]:
        """扫描所有数据集并检测格式"""
        logger.info("[SCAN] 开始扫描数据集: %s", self.dataset_base_dir)

        if not self.dataset_base_dir.exists():
            logger.warning("[SCAN] 数据集目录不存在: %s", self.dataset_base_dir)
            return []

        datasets = []
        total_dirs = 0
        valid_datasets = 0

        for item in sorted(self.dataset_base_dir.iterdir()):
            if not item.is_dir() or item.name.startswith("."):
                continue

            total_dirs += 1

            try:
                status = self._analyze_dataset(item)
                datasets.append(status)
                valid_datasets += 1

                # 合并为一条结构化日志
                logger.info("[DATASET] name=%s | format=%s | ready=%s | images=%d | labels=%d | classes=%s",
                           status.name, status.format.value, status.is_ready,
                           status.image_count, status.label_count, status.classes)

                if status.issues:
                    logger.warning("[ISSUE] %s: %s", status.name, "; ".join(status.issues))

            except Exception as e:
                logger.error("[ERROR] 分析失败 %s: %s", item.name, e)
                datasets.append(DatasetStatus(
                    name=item.name,
                    path=item,
                    format=DatasetFormat.UNKNOWN,
                    is_ready=False,
                    needs_conversion=False,
                    issues=[f"分析失败: {e}"]
                ))

        logger.info("[SCAN] 完成: 总计 %d 个目录，有效数据集 %d 个", total_dirs, valid_datasets)

        return datasets

    def _analyze_dataset(self, path: Path) -> DatasetStatus:
        """分析单个数据集"""
        scanner = DatasetScanner(str(path))
        profile = scanner.scan()

        # 检测数据集格式
        fmt, is_ready, needs_conversion = self._detect_format(path, profile)

        # 获取类别信息
        classes = []
        if profile.classes:
            classes = profile.classes
        elif profile.splits:
            # 从 splits 中提取类别名（针对 YOLO_CLASS_SUBDIRS 结构）
            all_classes = set()
            for split_data in profile.splits.values():
                if "classes" in split_data:
                    all_classes.update(split_data["classes"])
            classes = sorted(all_classes)

        return DatasetStatus(
            name=path.name,
            path=path,
            format=fmt,
            is_ready=is_ready,
            needs_conversion=needs_conversion,
            image_count=profile.image_count,
            label_count=profile.label_count,
            classes=classes,
            issues=profile.issues
        )

    def _detect_format(self, path: Path, profile: DatasetProfile) -> tuple[DatasetFormat, bool, bool]:
        """检测数据集格式"""
        # 检查是否是YOLO格式（有labels目录且有标注文件）
        has_labels_dir = (path / "labels").exists()
        has_annotations = profile.label_count > 0

        if has_labels_dir and has_annotations:
            return DatasetFormat.YOLO, True, False

        # 检查是否是分类格式
        # 情况1: 标准 images/{split}/{class}/ 结构
        images_dir = path / "images"
        if images_dir.exists():
            for split in ["train", "val", "test"]:
                split_dir = images_dir / split
                if split_dir.exists():
                    class_dirs = [d for d in split_dir.iterdir()
                                  if d.is_dir() and not d.name.startswith(".")]
                    if class_dirs:
                        return DatasetFormat.CLASSIFICATION, False, True

        # 情况2: 直接 {split}/{class}/ 结构（无images包装）
        for split in ["train", "val", "test"]:
            split_dir = path / split
            if split_dir.exists():
                class_dirs = [d for d in split_dir.iterdir()
                              if d.is_dir() and not d.name.startswith(".")]
                if class_dirs:
                    return DatasetFormat.CLASSIFICATION, False, True

        return DatasetFormat.UNKNOWN, False, False

    def convert_dataset(self, dataset_name: str, delete_original: bool = False) -> dict:
        """
        转换非YOLO格式数据集为YOLO格式

        Args:
            dataset_name: 数据集名称
            delete_original: 转换成功后是否删除原始数据集

        Returns:
            转换结果信息
        """
        logger.info("[CONVERT] 开始转换: %s (删除原始=%s)", dataset_name, delete_original)

        src_path = self.dataset_base_dir / dataset_name

        if not src_path.exists():
            error_msg = f"数据集不存在: {src_path}"
            logger.error("[CONVERT] %s", error_msg)
            raise ValueError(error_msg)

        # 分析源数据集
        status = self._analyze_dataset(src_path)
        if not status.needs_conversion:
            msg = f"数据集 '{dataset_name}' 已经是YOLO格式，无需转换"
            logger.info("[CONVERT] %s", msg)
            return {
                "success": False,
                "message": msg
            }

        if status.format == DatasetFormat.UNKNOWN:
            error_msg = f"无法识别的数据集格式: {dataset_name}"
            logger.error("[CONVERT] %s", error_msg)
            raise ValueError(error_msg)

        # 生成目标路径
        dest_name = f"{dataset_name}-yolo"
        dest_path = self.dataset_base_dir / dest_name

        try:
            # 执行转换
            stats = convert_classification_to_yolo(
                src_dir=str(src_path),
                dest_dir=str(dest_path)
            )

            logger.info("[CONVERT] 成功: %s -> %s | 总计 %d 张图像",
                       dataset_name, dest_name, sum(stats.values()))

            # 删除原始数据集
            if delete_original:
                try:
                    shutil.rmtree(src_path)
                    logger.info("[CLEANUP] 已删除原始数据集: %s", src_path)
                except Exception as e:
                    logger.warning("[CLEANUP] 删除原始数据集失败 %s: %s", src_path, e)

            result = {
                "success": True,
                "message": f"数据集 '{dataset_name}' 转换成功",
                "original_name": dataset_name,
                "converted_name": dest_name,
                "original_path": str(src_path),
                "converted_path": str(dest_path),
                "stats": stats,
                "deleted_original": delete_original
            }

            return result

        except Exception as e:
            logger.error("[CONVERT] 失败 %s: %s", dataset_name, e)
            logger.exception("[CONVERT] 详细错误信息:")

            # 清理可能部分创建的目标目录
            if dest_path.exists():
                try:
                    shutil.rmtree(dest_path)
                    logger.info("[CLEANUP] 已清理部分转换的目录: %s", dest_path)
                except Exception as e:
                    logger.warning("[CLEANUP] 清理部分转换目录失败 %s: %s", dest_path, e)
            raise

    def convert_all_datasets(self, delete_original: bool = False) -> list[dict]:
        """转换所有需要转换的数据集"""
        logger.info("[CONVERT_ALL] 开始批量转换 (删除原始=%s)", delete_original)

        datasets = self.scan_all_datasets()
        results = []

        to_convert = [ds for ds in datasets if ds.needs_conversion]

        if not to_convert:
            logger.info("[CONVERT_ALL] 没有需要转换的数据集")
            return results

        logger.info("[CONVERT_ALL] 发现 %d 个需要转换的数据集: %s",
                   len(to_convert), ", ".join(ds.name for ds in to_convert))

        for ds in to_convert:
            try:
                result = self.convert_dataset(ds.name, delete_original)
                results.append(result)
            except Exception as e:
                logger.error("[CONVERT_ALL] 转换失败 '%s': %s", ds.name, e)
                results.append({
                    "success": False,
                    "message": f"转换 '{ds.name}' 失败: {e}",
                    "dataset_name": ds.name
                })

        success_count = sum(1 for r in results if r.get("success"))
        fail_count = sum(1 for r in results if not r.get("success"))

        logger.info("[CONVERT_ALL] 完成: 成功 %d 个，失败 %d 个", success_count, fail_count)

        return results

    def list_ready_datasets(self) -> list[str]:
        """列出所有可以直接用于训练的数据集（快速检查，仅检测 data.yaml 存在性）"""
        if not self.dataset_base_dir.exists():
            return []

        ready = []
        for item in sorted(self.dataset_base_dir.iterdir()):
            if not item.is_dir() or item.name.startswith("."):
                continue
            # 快速检查：有 data.yaml 就认为是 YOLO 格式
            if (item / "data.yaml").exists():
                ready.append(item.name)

        return ready

    def get_dataset_info(self, dataset_name: str) -> DatasetStatus | None:
        """获取指定数据集的详细信息"""
        path = self.dataset_base_dir / dataset_name
        if not path.exists():
            return None
        return self._analyze_dataset(path)


def auto_manage_datasets(dataset_base_dir: str, auto_convert: bool = True) -> dict:
    """
    便捷函数：自动管理数据集

    Args:
        dataset_base_dir: 数据集基础目录
        auto_convert: 是否自动转换非YOLO格式数据集

    Returns:
        管理结果信息
    """
    manager = AutoDatasetManager(dataset_base_dir)

    # 扫描所有数据集
    datasets = manager.scan_all_datasets()

    result = {
        "total": len(datasets),
        "ready": [],
        "converted": [],
        "failed": [],
        "unknown": []
    }

    # 分类数据集
    for ds in datasets:
        if ds.is_ready:
            result["ready"].append(ds.name)
        elif ds.needs_conversion:
            if auto_convert:
                try:
                    convert_result = manager.convert_dataset(ds.name)
                    result["converted"].append(convert_result)
                except Exception as e:
                    result["failed"].append({
                        "name": ds.name,
                        "error": str(e)
                    })
            else:
                result["unknown"].append(ds.name)
        else:
            result["unknown"].append(ds.name)

    return result


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    if len(sys.argv) < 2:
        print("用法: python dataset_manager.py <数据集目录路径> [--no-auto-convert]")
        print("示例: python dataset_manager.py dataset/")
        print("示例: python dataset_manager.py dataset/ --no-auto-convert")
        sys.exit(1)

    dataset_dir = sys.argv[1]
    auto_convert = "--no-auto-convert" not in sys.argv

    print(f"数据集目录: {dataset_dir}")
    print(f"自动转换: {'启用' if auto_convert else '禁用'}")
    print()

    result = auto_manage_datasets(dataset_dir, auto_convert)

    print("\n" + "=" * 60)
    print("数据集管理结果")
    print("=" * 60)
    print(f"总计数据集: {result['total']}")
    print(f"可直接训练: {len(result['ready'])}")
    print(f"已转换: {len(result['converted'])}")
    print(f"转换失败: {len(result['failed'])}")
    print(f"未知格式: {len(result['unknown'])}")

    if result['ready']:
        print("\n可直接训练的数据集:")
        for name in result['ready']:
            print(f"  [OK] {name}")

    if result['converted']:
        print("\n已转换的数据集:")
        for conv in result['converted']:
            print(f"  [OK] {conv['original_name']} -> {conv['converted_name']}")
            if 'stats' in conv:
                for split, count in conv['stats'].items():
                    print(f"    {split}: {count} 张图像")

    if result['failed']:
        print("\n转换失败的数据集:")
        for fail in result['failed']:
            print(f"  [FAIL] {fail['name']}: {fail['error']}")

    if result['unknown']:
        print("\n未知格式的数据集:")
        for name in result['unknown']:
            print(f"  [?] {name}")
