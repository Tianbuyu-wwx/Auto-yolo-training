"""
数据验证管道模块
负责在训练前对数据集进行全面质量检查
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import cv2
import yaml

from src.utils import imread_unicode


class Severity(Enum):
    """问题严重程度"""
    ERROR = "error"       # 阻塞性问题，必须修复
    WARNING = "warning"   # 警告，建议修复
    INFO = "info"         # 提示信息


@dataclass
class ValidationIssue:
    """验证问题记录"""
    severity: Severity
    category: str
    message: str
    file_path: str | None = None
    details: dict | None = None


@dataclass
class ValidationReport:
    """验证报告"""
    dataset_name: str
    dataset_path: str
    is_valid: bool = True
    issues: list[ValidationIssue] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def add_issue(self, issue: ValidationIssue):
        self.issues.append(issue)
        if issue.severity == Severity.ERROR:
            self.is_valid = False

    def get_errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    def get_warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]

    def to_dict(self) -> dict:
        return {
            "dataset_name": self.dataset_name,
            "dataset_path": self.dataset_path,
            "is_valid": self.is_valid,
            "error_count": len(self.get_errors()),
            "warning_count": len(self.get_warnings()),
            "stats": self.stats,
            "issues": [
                {
                    "severity": i.severity.value,
                    "category": i.category,
                    "message": i.message,
                    "file": i.file_path,
                    "details": i.details
                }
                for i in self.issues
            ]
        }


class DataValidator:
    """YOLO数据集验证器"""

    SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

    def __init__(self, dataset_path: str):
        self.dataset_path = Path(dataset_path)
        self.dataset_name = self.dataset_path.name
        self.report = ValidationReport(
            dataset_name=self.dataset_name,
            dataset_path=str(self.dataset_path)
        )

    def validate(self) -> ValidationReport:
        """执行完整验证流程"""
        self._check_directory_structure()
        if not self.report.is_valid:
            return self.report

        self._validate_images()
        self._validate_labels()
        self._validate_image_label_pairs()
        self._validate_class_consistency()
        self._compute_statistics()
        self._check_dataset_size()
        self._check_class_balance()

        return self.report

    def _check_directory_structure(self):
        """检查目录结构是否符合YOLO标准（支持类别子目录）"""
        required_dirs = ["images/train", "images/val", "labels/train", "labels/val"]
        optional_dirs = ["images/test", "labels/test"]

        for dir_path in required_dirs:
            full_path = self.dataset_path / dir_path
            if not full_path.exists():
                self.report.add_issue(ValidationIssue(
                    severity=Severity.ERROR,
                    category="directory_structure",
                    message=f"缺少必需目录: {dir_path}",
                    file_path=str(full_path)
                ))

        for dir_path in optional_dirs:
            full_path = self.dataset_path / dir_path
            if not full_path.exists():
                self.report.add_issue(ValidationIssue(
                    severity=Severity.INFO,
                    category="directory_structure",
                    message=f"可选目录不存在: {dir_path}",
                    file_path=str(full_path)
                ))

    def _find_images_in_split(self, split: str) -> list[Path]:
        """查找指定split的所有图像文件（支持类别子目录）"""
        img_dir = self.dataset_path / "images" / split
        if not img_dir.exists():
            return []

        images = []
        for img_file in img_dir.rglob("*"):
            if img_file.is_file() and img_file.suffix.lower() in self.SUPPORTED_IMAGE_EXTS:
                images.append(img_file)
        return images

    def _find_labels_in_split(self, split: str) -> list[Path]:
        """查找指定split的所有标注文件（支持类别子目录）"""
        label_dir = self.dataset_path / "labels" / split
        if not label_dir.exists():
            return []

        labels = []
        for label_file in label_dir.rglob("*.txt"):
            if label_file.is_file():
                labels.append(label_file)
        return labels

    def _validate_images(self):
        """验证图像文件（支持类别子目录）"""
        for split in ["train", "val", "test"]:
            images = self._find_images_in_split(split)

            for img_file in images:
                if img_file.suffix.lower() not in self.SUPPORTED_IMAGE_EXTS:
                    self.report.add_issue(ValidationIssue(
                        severity=Severity.WARNING,
                        category="image_format",
                        message=f"不支持的图像格式: {img_file.suffix}",
                        file_path=str(img_file)
                    ))
                    continue

                img = imread_unicode(str(img_file), cv2.IMREAD_UNCHANGED)
                if img is None:
                    # 尝试用二进制方式检查文件是否存在且非空
                    try:
                        file_size = img_file.stat().st_size
                        if file_size == 0:
                            self.report.add_issue(ValidationIssue(
                                severity=Severity.ERROR,
                                category="image_empty",
                                message="图像文件大小为0字节",
                                file_path=str(img_file),
                                details={"file_size": file_size}
                            ))
                        else:
                            self.report.add_issue(ValidationIssue(
                                severity=Severity.WARNING,
                                category="image_read_failed",
                                message=f"图像文件读取失败（可能是路径编码问题或格式不支持），文件大小: {file_size}字节",
                                file_path=str(img_file),
                                details={"file_size": file_size}
                            ))
                    except OSError:
                        self.report.add_issue(ValidationIssue(
                            severity=Severity.ERROR,
                            category="image_corrupted",
                            message="图像文件损坏或无法访问",
                            file_path=str(img_file)
                        ))
                    continue

                h, w = img.shape[:2]
                if h == 0 or w == 0:
                    self.report.add_issue(ValidationIssue(
                        severity=Severity.ERROR,
                        category="image_dimension",
                        message=f"图像尺寸异常: {w}x{h}",
                        file_path=str(img_file),
                        details={"width": w, "height": h}
                    ))

    def _validate_labels(self):
        """验证标注文件格式（支持类别子目录）"""
        for split in ["train", "val", "test"]:
            labels = self._find_labels_in_split(split)

            for label_file in labels:
                with open(label_file, encoding="utf-8") as f:
                    lines = f.readlines()

                for line_no, line in enumerate(lines, 1):
                    line = line.strip()
                    if not line:
                        continue

                    parts = line.split()
                    if len(parts) != 5:
                        self.report.add_issue(ValidationIssue(
                            severity=Severity.ERROR,
                            category="label_format",
                            message=f"标注格式错误，期望5个值，实际{len(parts)}个",
                            file_path=str(label_file),
                            details={"line_no": line_no, "content": line}
                        ))
                        continue

                    try:
                        _cls_id = int(parts[0])
                        x, y, w, h = map(float, parts[1:])
                    except ValueError:
                        self.report.add_issue(ValidationIssue(
                            severity=Severity.ERROR,
                            category="label_format",
                            message="标注值类型转换失败",
                            file_path=str(label_file),
                            details={"line_no": line_no, "content": line}
                        ))
                        continue

                    if not (0 <= x <= 1 and 0 <= y <= 1 and 0 <= w <= 1 and 0 <= h <= 1):
                        self.report.add_issue(ValidationIssue(
                            severity=Severity.ERROR,
                            category="label_out_of_bounds",
                            message=f"标注值越界: x={x}, y={y}, w={w}, h={h}",
                            file_path=str(label_file),
                            details={"line_no": line_no, "values": [x, y, w, h]}
                        ))

                    if w <= 0 or h <= 0:
                        self.report.add_issue(ValidationIssue(
                            severity=Severity.ERROR,
                            category="label_zero_size",
                            message=f"标注框尺寸为零或负数: w={w}, h={h}",
                            file_path=str(label_file),
                            details={"line_no": line_no}
                        ))

    def _validate_image_label_pairs(self):
        """验证图像与标注文件配对（支持类别子目录）"""
        for split in ["train", "val", "test"]:
            img_dir = self.dataset_path / "images" / split
            label_dir = self.dataset_path / "labels" / split

            if not img_dir.exists() or not label_dir.exists():
                continue

            # 使用递归查找所有图像和标注文件
            images = {f.stem for f in self._find_images_in_split(split)}
            labels = {f.stem for f in self._find_labels_in_split(split)}

            missing_labels = images - labels
            for stem in missing_labels:
                self.report.add_issue(ValidationIssue(
                    severity=Severity.WARNING,
                    category="missing_label",
                    message="图像缺少对应标注文件",
                    file_path=str(img_dir / f"{stem}.*")
                ))

            orphan_labels = labels - images
            for stem in orphan_labels:
                self.report.add_issue(ValidationIssue(
                    severity=Severity.WARNING,
                    category="orphan_label",
                    message="标注文件缺少对应图像",
                    file_path=str(label_dir / f"{stem}.txt")
                ))

    def _validate_class_consistency(self):
        """验证类别一致性"""
        # YOLO data.yaml belongs to the dataset root, not its parent directory.
        data_yaml = self.dataset_path / "data.yaml"
        if data_yaml.exists():
            try:
                with open(data_yaml, encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                expected_classes = config.get("nc", 0)
                expected_names = config.get("names", [])

                actual_classes = set()
                for split in ["train", "val", "test"]:
                    label_dir = self.dataset_path / "labels" / split
                    if not label_dir.exists():
                        continue
                    for label_file in label_dir.rglob("*.txt"):
                        if not label_file.is_file():
                            continue
                        with open(label_file, encoding="utf-8") as f:
                            for line in f:
                                line = line.strip()
                                if line:
                                    try:
                                        cls_id = int(line.split()[0])
                                        actual_classes.add(cls_id)
                                    except (ValueError, IndexError):
                                        pass

                max_class = max(actual_classes) if actual_classes else -1
                if max_class >= expected_classes:
                    self.report.add_issue(ValidationIssue(
                        severity=Severity.ERROR,
                        category="class_mismatch",
                        message=f"标注中的类别ID({max_class})超出data.yaml声明的类别数({expected_classes})",
                        details={"expected": expected_classes, "actual_max": max_class}
                    ))

                self.report.stats["expected_classes"] = expected_classes
                self.report.stats["class_names"] = expected_names
            except Exception as e:
                self.report.add_issue(ValidationIssue(
                    severity=Severity.WARNING,
                    category="config_error",
                    message=f"读取data.yaml失败: {e}",
                    file_path=str(data_yaml)
                ))

    def _compute_statistics(self):
        """计算数据集统计信息"""
        stats = {"splits": {}}
        total_images = 0
        total_labels = 0
        all_class_ids = set()

        for split in ["train", "val", "test"]:
            img_dir = self.dataset_path / "images" / split
            label_dir = self.dataset_path / "labels" / split

            img_count = 0
            label_count = 0
            bbox_count = 0
            class_distribution = {}

            if img_dir.exists():
                img_count = len([f for f in img_dir.rglob("*")
                                if f.suffix.lower() in self.SUPPORTED_IMAGE_EXTS and f.is_file()])

            if label_dir.exists():
                for label_file in label_dir.rglob("*.txt"):
                    if not label_file.is_file():
                        continue
                    label_count += 1
                    with open(label_file, encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                bbox_count += 1
                                try:
                                    cls_id = int(line.split()[0])
                                    all_class_ids.add(cls_id)
                                    class_distribution[cls_id] = class_distribution.get(cls_id, 0) + 1
                                except (ValueError, IndexError):
                                    pass

            stats["splits"][split] = {
                "images": img_count,
                "labels": label_count,
                "bounding_boxes": bbox_count,
                "class_distribution": class_distribution
            }
            total_images += img_count
            total_labels += label_count

        stats["total_images"] = total_images
        stats["total_labels"] = total_labels
        stats["unique_classes"] = sorted(all_class_ids)
        self.report.stats.update(stats)

    def _check_dataset_size(self):
        """检查数据集规模"""
        train_images = self.report.stats.get("splits", {}).get("train", {}).get("images", 0)
        val_images = self.report.stats.get("splits", {}).get("val", {}).get("images", 0)

        if train_images < 50:
            self.report.add_issue(ValidationIssue(
                severity=Severity.WARNING,
                category="dataset_size",
                message=f"训练集图像数量过少({train_images}张)，建议至少50张以上",
                details={"train_images": train_images}
            ))

        if val_images < 10:
            self.report.add_issue(ValidationIssue(
                severity=Severity.WARNING,
                category="dataset_size",
                message=f"验证集图像数量过少({val_images}张)，建议至少10张以上",
                details={"val_images": val_images}
            ))

        if train_images > 0 and val_images > 0:
            ratio = val_images / train_images
            if ratio < 0.1:
                self.report.add_issue(ValidationIssue(
                    severity=Severity.WARNING,
                    category="split_ratio",
                    message=f"验证集比例过低({ratio:.2%})，建议至少10%",
                    details={"train": train_images, "val": val_images, "ratio": ratio}
                ))

    def _check_class_balance(self):
        """检查类别平衡性"""
        for split in ["train", "val"]:
            split_stats = self.report.stats.get("splits", {}).get(split, {})
            class_dist = split_stats.get("class_distribution", {})

            if len(class_dist) < 2:
                continue

            values = list(class_dist.values())
            if min(values) > 0:
                imbalance_ratio = max(values) / min(values)
                if imbalance_ratio > 10:
                    self.report.add_issue(ValidationIssue(
                        severity=Severity.WARNING,
                        category="class_imbalance",
                        message=f"{split}集类别严重不平衡，最大/最小比例={imbalance_ratio:.1f}",
                        details={"distribution": class_dist, "ratio": imbalance_ratio}
                    ))


def validate_dataset(dataset_path: str) -> ValidationReport:
    """便捷函数：验证数据集"""
    validator = DataValidator(dataset_path)
    return validator.validate()


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("用法: python data_validator.py <dataset_path>")
        sys.exit(1)

    dataset_path = sys.argv[1]
    report = validate_dataset(dataset_path)

    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    sys.exit(0 if report.is_valid else 1)
