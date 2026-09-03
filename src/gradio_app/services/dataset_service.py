"""
数据集操作服务
"""

import logging
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any

from src.constants import ProjectPaths
from src.dataset_manager import AutoDatasetManager

logger = logging.getLogger(__name__)


class DatasetService:
    """数据集管理服务"""

    # ZIP解压安全限制
    MAX_ZIP_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
    MAX_ZIP_FILE_COUNT = 100000
    MAX_SINGLE_FILE_SIZE = 500 * 1024 * 1024  # 500MB

    SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.paths = ProjectPaths(base_dir)
        self.dataset_dir = self.paths.dataset_dir
        self.manager = AutoDatasetManager(str(self.dataset_dir))

    def list_datasets(self) -> list[str]:
        """列出所有可用数据集"""
        return self.manager.list_ready_datasets()

    def get_all_statuses(self) -> list[dict]:
        """获取所有数据集状态"""
        datasets = self.manager.scan_all_datasets()
        return [
            {
                "name": ds.name,
                "format": ds.format.value,
                "is_ready": ds.is_ready,
                "needs_conversion": ds.needs_conversion,
                "image_count": ds.image_count,
                "label_count": ds.label_count,
                "classes": ds.classes,
                "issues": ds.issues,
            }
            for ds in datasets
        ]

    def get_info(self, dataset_name: str) -> dict[str, Any]:
        """获取数据集详情"""
        dataset_path = self.dataset_dir / dataset_name
        if not dataset_path.exists():
            return {"error": f"数据集不存在: {dataset_name}"}

        info = {"name": dataset_name, "path": str(dataset_path), "splits": {}}

        for split in ["train", "val", "test"]:
            img_dir = dataset_path / "images" / split
            label_dir = dataset_path / "labels" / split

            img_count = 0
            label_count = 0

            if img_dir.exists():
                img_count = len([f for f in img_dir.rglob("*")
                                if f.suffix.lower() in self.SUPPORTED_IMAGE_EXTS and f.is_file()])

            if label_dir.exists():
                label_count = len([f for f in label_dir.rglob("*.txt") if f.is_file()])

            info["splits"][split] = {
                "images": img_count,
                "labels": label_count,
            }

        info["total_images"] = sum(s["images"] for s in info["splits"].values())

        # 获取样本图像
        sample_images = []
        train_dir = dataset_path / "images" / "train"
        if train_dir.exists():
            for img in list(train_dir.iterdir())[:4]:
                if img.suffix.lower() in self.SUPPORTED_IMAGE_EXTS:
                    sample_images.append(str(img))

        info["sample_images"] = sample_images
        return info

    def extract(self, zip_path: str, dataset_name: str | None = None) -> dict[str, str]:
        """解压数据集ZIP"""
        zip_path = Path(zip_path)
        if not zip_path.exists():
            return {"status": "error", "message": f"文件不存在: {zip_path}"}

        if not dataset_name:
            dataset_name = zip_path.stem

        target_dir = self.dataset_dir / dataset_name

        try:
            if target_dir.exists():
                shutil.rmtree(target_dir)

            with zipfile.ZipFile(zip_path, 'r') as zf:
                total_size = sum(info.file_size for info in zf.infolist())
                if total_size > self.MAX_ZIP_SIZE:
                    return {"status": "error", "message": f"ZIP文件过大（{total_size / (1024**3):.1f}GB），超过2GB限制"}

                if len(zf.infolist()) > self.MAX_ZIP_FILE_COUNT:
                    return {"status": "error", "message": f"ZIP内文件数量过多（{len(zf.infolist())}），超过100000限制"}

                for info in zf.infolist():
                    if info.filename.startswith('/') or '..' in info.filename.split('/'):
                        return {"status": "error", "message": f"ZIP包含不安全路径: {info.filename}"}
                    if info.file_size > self.MAX_SINGLE_FILE_SIZE:
                        return {"status": "error", "message": f"文件过大: {info.filename}（{info.file_size / (1024**2):.0f}MB）"}

                zf.extractall(target_dir)

            # 处理嵌套目录
            for _ in range(5):
                if not self._flatten_nested_dir(target_dir):
                    break

            return {
                "status": "success",
                "message": f"数据集 '{dataset_name}' 解压成功",
                "path": str(target_dir),
                "dataset_name": dataset_name,
            }

        except Exception as e:
            return {"status": "error", "message": f"解压失败: {str(e)}"}

    def validate(self, dataset_name: str) -> dict[str, Any]:
        """验证数据集"""
        dataset_path = self.dataset_dir / dataset_name
        if not dataset_path.exists():
            return {"status": "error", "message": f"数据集不存在: {dataset_name}"}

        try:
            import io
            old_stderr = sys.stderr
            sys.stderr = io.StringIO()

            from src.data_validator import validate_dataset
            report = validate_dataset(str(dataset_path))

            sys.stderr = old_stderr

            errors = report.get_errors()
            warnings_list = report.get_warnings()

            warning_categories = {}
            for w in warnings_list:
                cat = w.category
                warning_categories[cat] = warning_categories.get(cat, 0) + 1

            error_categories = {}
            for e in errors:
                cat = e.category
                error_categories[cat] = error_categories.get(cat, 0) + 1

            return {
                "status": "success" if report.is_valid else "warning",
                "is_valid": report.is_valid,
                "error_count": len(errors),
                "warning_count": len(warnings_list),
                "error_categories": error_categories,
                "warning_categories": warning_categories,
                "stats": report.stats,
                "message": self._format_validation_message(report, errors, warnings_list),
            }

        except Exception as e:
            sys.stderr = old_stderr
            return {"status": "error", "message": f"验证失败: {str(e)}"}

    def _flatten_nested_dir(self, target_dir: Path) -> bool:
        """处理嵌套目录"""
        dataset_root = self._find_dataset_root(target_dir)
        if dataset_root == target_dir:
            return False

        for item in dataset_root.iterdir():
            dest = target_dir / item.name
            if dest.exists():
                shutil.rmtree(dest) if dest.is_dir() else dest.unlink()
            shutil.move(str(item), str(dest))

        current = dataset_root
        while current != target_dir:
            parent = current.parent
            current.rmdir()
            current = parent
        return True

    def _find_dataset_root(self, path: Path, depth: int = 0) -> Path:
        """递归查找包含 images/train 的目录"""
        if depth > 5:
            return path
        if (path / "images" / "train").exists():
            return path
        subdirs = [d for d in path.iterdir() if d.is_dir()]
        if len(subdirs) == 1:
            return self._find_dataset_root(subdirs[0], depth + 1)
        return path

    def _format_validation_message(self, report, errors, warnings_list) -> str:
        lines = []
        if not report.is_valid:
            lines.append("数据验证未通过，存在阻塞性问题")
        elif warnings_list:
            lines.append("数据验证通过，但存在建议优化项")
        else:
            lines.append("数据验证完全通过")

        cat_names = {
            "directory_structure": "目录结构", "image_format": "图像格式",
            "image_read_failed": "图像读取失败", "image_dimension": "图像尺寸异常",
            "label_format": "标注格式错误", "label_out_of_bounds": "标注值越界",
            "label_zero_size": "标注框尺寸为零", "missing_label": "缺少标注文件",
            "orphan_label": "孤立标注文件", "class_mismatch": "类别不匹配",
            "config_error": "配置文件错误", "dataset_size": "数据集规模",
            "split_ratio": "划分比例", "class_imbalance": "类别不平衡",
        }

        if errors:
            lines.append(f"\n**错误 ({len(errors)}个):**")
            for e in errors:
                lines.append(f"  - {cat_names.get(e.category, e.category)}: {e.message[:80]}")

        if warnings_list:
            lines.append(f"\n**警告 ({len(warnings_list)}个):**")
            grouped = {}
            for w in warnings_list:
                name = cat_names.get(w.category, w.category)
                grouped[name] = grouped.get(name, 0) + 1
            for name, count in grouped.items():
                lines.append(f"  - {name}: {count}个")

        stats = report.stats
        if "splits" in stats:
            lines.append("\n**数据集统计:**")
            for split, data in stats["splits"].items():
                if data.get("images", 0) > 0:
                    lines.append(f"  - {split}: {data['images']}张图像, {data.get('labels', 0)}个标注")

        return "\n".join(lines)
