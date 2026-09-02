"""
自适应数据集扫描与加载模块
支持多种目录结构和组织方式的数据集自动识别与加载
"""

import os
import cv2
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Set, Iterator
from enum import Enum
import logging

from src.utils import imread_unicode

logger = logging.getLogger(__name__)


class DatasetStructure(Enum):
    """数据集结构类型"""
    YOLO_STANDARD = "yolo_standard"           # images/{train,val,test} + labels/{train,val,test}
    YOLO_CLASS_SUBDIRS = "yolo_class_subdirs" # images/{split}/{class} + labels/{split}/{class}
    FLAT = "flat"                             # 所有文件在同一目录
    NESTED = "nested"                         # 多层嵌套目录
    UNKNOWN = "unknown"                       # 无法识别


@dataclass
class ImageInfo:
    """图像文件信息"""
    path: Path
    split: str
    class_name: Optional[str] = None
    label_path: Optional[Path] = None
    width: int = 0
    height: int = 0
    channels: int = 0


@dataclass
class DatasetProfile:
    """数据集特征档案"""
    name: str
    path: Path
    structure: DatasetStructure
    splits: Dict[str, Dict] = field(default_factory=dict)
    classes: List[str] = field(default_factory=list)
    image_count: int = 0
    label_count: int = 0
    issues: List[str] = field(default_factory=list)


class DatasetScanner:
    """自适应数据集扫描器"""

    SUPPORTED_IMAGE_EXTS: Set[str] = {
        ".jpg", ".jpeg", ".png", ".bmp", ".webp",
        ".gif", ".tiff", ".tif", ".jfif", ".jpe"
    }
    SUPPORTED_LABEL_EXTS: Set[str] = {".txt", ".xml", ".json", ".csv"}

    def __init__(self, dataset_path: str):
        self.dataset_path = Path(dataset_path).resolve()
        self.dataset_name = self.dataset_path.name
        self.profile = DatasetProfile(
            name=self.dataset_name,
            path=self.dataset_path,
            structure=DatasetStructure.UNKNOWN,
            splits={},
            classes=[],
            image_count=0,
            label_count=0,
            issues=[]
        )

    def scan(self) -> DatasetProfile:
        """执行完整扫描"""
        if not self.dataset_path.exists():
            self.profile.issues.append(f"数据集路径不存在: {self.dataset_path}")
            return self.profile

        if not self.dataset_path.is_dir():
            self.profile.issues.append(f"路径不是目录: {self.dataset_path}")
            return self.profile

        try:
            structure = self._detect_structure()
            self.profile.structure = structure
            logger.info(f"检测到数据集结构: {structure.value} - {self.dataset_name}")

            self._scan_images()
            self._scan_labels()
            self._match_image_label_pairs()
            self._detect_classes()
            self._validate_completeness()

        except PermissionError as e:
            self.profile.issues.append(f"权限错误: {e}")
        except OSError as e:
            self.profile.issues.append(f"系统错误: {e}")
        except Exception as e:
            self.profile.issues.append(f"扫描异常: {e}")
            logger.exception(f"扫描数据集时发生异常: {self.dataset_name}")

        return self.profile

    def _detect_structure(self) -> DatasetStructure:
        """检测数据集目录结构类型"""
        has_images = (self.dataset_path / "images").exists()
        has_labels = (self.dataset_path / "labels").exists()

        standard_splits = []
        if has_images:
            images_dir = self.dataset_path / "images"
            splits = ["train", "val", "test"]

            # 检查标准YOLO结构: images/{train,val,test}
            standard_splits = [s for s in splits if (images_dir / s).exists()]
            if standard_splits:
                # 检查是否有类别子目录（排除隐藏目录）
                has_class_subdirs = False
                for split in standard_splits:
                    split_dir = images_dir / split
                    subdirs = [d for d in split_dir.iterdir() 
                               if d.is_dir() and not d.name.startswith(".") and d.name != "__pycache__"]
                    if subdirs:
                        has_class_subdirs = True
                        break

                if has_class_subdirs:
                    return DatasetStructure.YOLO_CLASS_SUBDIRS
                return DatasetStructure.YOLO_STANDARD

        # 检查是否有图像文件直接在当前目录（扁平结构）
        root_images = [
            f for f in self.dataset_path.iterdir()
            if f.is_file() and f.suffix.lower() in self.SUPPORTED_IMAGE_EXTS
        ]
        if root_images:
            return DatasetStructure.FLAT

        # 检查是否有图像文件在子目录中（嵌套结构）
        # 排除标准YOLO目录结构，避免误判
        def is_standard_yolo_subdir(path: Path) -> bool:
            """检查路径是否是标准YOLO子目录"""
            parts = [p.lower() for p in path.parts]
            # 检查是否同时包含 images 和 train/val/test
            has_images = "images" in parts
            has_labels = "labels" in parts
            has_split = any(s in parts for s in ["train", "val", "test"])
            # 如果是标准YOLO结构（同时有images和split）则排除
            if has_images and has_split:
                return True
            # 如果同时有images和labels目录，也认为是标准结构
            if has_images and has_labels:
                return True
            return False

        # 对于嵌套结构，我们需要找到实际的图像文件并检查它们所在的路径
        all_images = list(self._find_image_files(self.dataset_path, max_depth=10))
        nested_images = [
            p for p in all_images
            if not is_standard_yolo_subdir(p)
        ]
        
        # 如果所有图像都在标准YOLO子目录中，但根目录没有images/train结构
        # 说明这是一个多层嵌套的YOLO结构（如 dataset/v1/train/images/）
        if all_images:
            # 尝试找到包含images/train的最深路径
            for img_path in all_images:
                if is_standard_yolo_subdir(img_path):
                    # 这是嵌套的YOLO结构
                    return DatasetStructure.NESTED
        
        if nested_images:
            return DatasetStructure.NESTED

        return DatasetStructure.UNKNOWN

    def _find_image_files(self, root: Path, max_depth: int = 10, current_depth: int = 0, skip_hidden: bool = True) -> Iterator[Path]:
        """递归查找图像文件"""
        if current_depth > max_depth:
            return

        try:
            for item in root.iterdir():
                if item.is_file() and item.suffix.lower() in self.SUPPORTED_IMAGE_EXTS:
                    yield item
                elif item.is_dir():
                    # 跳过隐藏目录
                    if skip_hidden and (item.name.startswith(".") or item.name == "__pycache__"):
                        continue
                    yield from self._find_image_files(item, max_depth, current_depth + 1, skip_hidden)
        except PermissionError:
            logger.warning(f"无法访问目录: {root}")
        except OSError as e:
            logger.warning(f"访问目录出错 {root}: {e}")

    def _scan_images(self):
        """扫描所有图像文件"""
        structure = self.profile.structure

        if structure == DatasetStructure.YOLO_STANDARD:
            self._scan_yolo_standard()
        elif structure == DatasetStructure.YOLO_CLASS_SUBDIRS:
            self._scan_yolo_class_subdirs()
        elif structure == DatasetStructure.NESTED:
            self._scan_nested()
        else:
            self._scan_flat()

    def _scan_yolo_standard(self):
        """扫描标准YOLO结构"""
        images_dir = self.dataset_path / "images"
        for split in ["train", "val", "test"]:
            split_dir = images_dir / split
            if not split_dir.exists():
                continue

            images = []
            for img_file in self._find_image_files(split_dir, max_depth=5):
                # 只统计当前目录或一级子目录中的图像
                rel_path = img_file.relative_to(split_dir)
                if len(rel_path.parts) <= 2:  # 最多允许1层子目录
                    images.append(ImageInfo(
                        path=img_file,
                        split=split,
                        class_name=None
                    ))

            if images:
                self.profile.splits[split] = {
                    "images": images,
                    "classes": set()
                }
                self.profile.image_count += len(images)

    def _scan_yolo_class_subdirs(self):
        """扫描带类别子目录的YOLO结构"""
        images_dir = self.dataset_path / "images"
        for split in ["train", "val", "test"]:
            split_dir = images_dir / split
            if not split_dir.exists():
                continue

            images = []
            classes = set()
            for class_dir in split_dir.iterdir():
                if not class_dir.is_dir():
                    continue
                # 跳过隐藏目录
                if class_dir.name.startswith(".") or class_dir.name == "__pycache__":
                    continue
                class_name = class_dir.name
                classes.add(class_name)

                for img_file in class_dir.iterdir():
                    if img_file.is_file() and img_file.suffix.lower() in self.SUPPORTED_IMAGE_EXTS:
                        images.append(ImageInfo(
                            path=img_file,
                            split=split,
                            class_name=class_name
                        ))

            if images:
                self.profile.splits[split] = {
                    "images": images,
                    "classes": classes
                }
                self.profile.image_count += len(images)
                self.profile.classes = sorted(list(set(self.profile.classes) | classes))

    def _scan_nested(self):
        """扫描嵌套结构，尝试按目录名推断split"""
        split_keywords = {
            "train": ["train", "training"],
            "val": ["val", "validation", "valid"],
            "test": ["test", "testing"]
        }

        # 尝试按目录名分组
        split_dirs: Dict[str, List[Path]] = {"train": [], "val": [], "test": []}
        unclassified = []

        for img_path in self._find_image_files(self.dataset_path):
            # 检查路径中是否包含split关键词
            path_parts = [p.lower() for p in img_path.parts]
            assigned = False
            for split, keywords in split_keywords.items():
                if any(kw in path_parts for kw in keywords):
                    split_dirs[split].append(img_path)
                    assigned = True
                    break
            if not assigned:
                unclassified.append(img_path)

        # 如果有未分类的，全部分到train
        if unclassified and not any(split_dirs.values()):
            split_dirs["train"] = unclassified
        elif unclassified:
            split_dirs["train"].extend(unclassified)

        for split, images_paths in split_dirs.items():
            if not images_paths:
                continue
            images = [ImageInfo(path=p, split=split) for p in images_paths]
            self.profile.splits[split] = {
                "images": images,
                "classes": set()
            }
            self.profile.image_count += len(images)

    def _scan_flat(self):
        """扫描扁平结构"""
        images = []
        for img_file in self.dataset_path.iterdir():
            if img_file.is_file() and img_file.suffix.lower() in self.SUPPORTED_IMAGE_EXTS:
                images.append(ImageInfo(path=img_file, split="train"))

        if images:
            self.profile.splits["train"] = {
                "images": images,
                "classes": set()
            }
            self.profile.image_count += len(images)

    def _scan_labels(self):
        """扫描标注文件"""
        if self.profile.structure == DatasetStructure.YOLO_CLASS_SUBDIRS:
            self._scan_labels_class_subdirs()
            return

        labels_dir = self.dataset_path / "labels"
        if not labels_dir.exists():
            self.profile.issues.append("未找到 labels 目录")
            return

        for split in ["train", "val", "test"]:
            split_label_dir = labels_dir / split
            if not split_label_dir.exists():
                continue

            label_count = 0
            for label_file in split_label_dir.iterdir():
                if label_file.is_file() and label_file.suffix == ".txt":
                    label_count += 1
                    # 尝试匹配到对应的图像
                    self._match_label_to_image(label_file, split)

            self.profile.label_count += label_count

    def _scan_labels_class_subdirs(self):
        """扫描带类别子目录的标注文件"""
        labels_dir = self.dataset_path / "labels"
        if not labels_dir.exists():
            self.profile.issues.append("未找到 labels 目录")
            return

        for split in ["train", "val", "test"]:
            split_label_dir = labels_dir / split
            if not split_label_dir.exists():
                continue

            for class_dir in split_label_dir.iterdir():
                if not class_dir.is_dir():
                    continue
                for label_file in class_dir.iterdir():
                    if label_file.is_file() and label_file.suffix == ".txt":
                        self.profile.label_count += 1
                        self._match_label_to_image(label_file, split, class_dir.name)

    def _match_label_to_image(self, label_path: Path, split: str, class_name: Optional[str] = None):
        """将标注文件匹配到对应的图像（使用字典索引优化）"""
        base_name = label_path.stem

        if split in self.profile.splits:
            # 使用索引字典加速查找（懒初始化）
            if not hasattr(self, '_image_stem_index') or split not in self._image_stem_index:
                if not hasattr(self, '_image_stem_index'):
                    self._image_stem_index = {}
                self._image_stem_index[split] = {
                    img.path.stem: img
                    for img in self.profile.splits[split]["images"]
                }

            img_info = self._image_stem_index[split].get(base_name)
            if img_info is not None:
                img_info.label_path = label_path
                if class_name:
                    img_info.class_name = class_name
                return

    def _match_image_label_pairs(self):
        """统计图像-标注匹配情况"""
        for split, data in self.profile.splits.items():
            images = data["images"]
            matched = sum(1 for img in images if img.label_path is not None)
            unmatched = len(images) - matched

            if unmatched > 0:
                self.profile.issues.append(
                    f"{split} 集中有 {unmatched}/{len(images)} 张图像缺少对应标注"
                )

    def _detect_classes(self):
        """检测数据集中的类别"""
        if self.profile.classes:
            return

        # 从标注文件中提取类别
        class_ids: Set[int] = set()
        for split, data in self.profile.splits.items():
            for img_info in data["images"]:
                if img_info.label_path and img_info.label_path.exists():
                    try:
                        with open(img_info.label_path, "r", encoding="utf-8") as f:
                            for line in f:
                                line = line.strip()
                                if line:
                                    parts = line.split()
                                    if parts:
                                        class_ids.add(int(parts[0]))
                    except Exception as e:
                        logger.warning(f"读取标注文件失败 {img_info.label_path}: {e}")

        if class_ids:
            self.profile.classes = [f"class_{i}" for i in sorted(class_ids)]

    def _validate_completeness(self):
        """验证数据集完整性"""
        if not self.profile.splits:
            self.profile.issues.append("未检测到任何图像文件")
            return

        # 检查是否有train集
        if "train" not in self.profile.splits:
            self.profile.issues.append("缺少 train 集（训练集是必需的）")

        # 检查图像尺寸（使用PIL仅读头部，避免全量解码）
        from PIL import Image as PILImage
        for split, data in self.profile.splits.items():
            for img_info in data["images"]:
                try:
                    with PILImage.open(str(img_info.path)) as pil_img:
                        w, h = pil_img.size
                        img_info.width = w
                        img_info.height = h
                        img_info.channels = len(pil_img.getbands())
                except Exception as e:
                    self.profile.issues.append(f"无法读取图像 {img_info.path}: {e}")

    @staticmethod
    def _safe_imread(path: str) -> Optional[np.ndarray]:
        """安全读取图像，支持中文路径"""
        return imread_unicode(path)

    def get_split_images(self, split: str) -> List[ImageInfo]:
        """获取指定split的所有图像"""
        if split in self.profile.splits:
            return self.profile.splits[split]["images"]
        return []

    def get_all_images(self) -> List[ImageInfo]:
        """获取所有图像"""
        all_images = []
        for data in self.profile.splits.values():
            all_images.extend(data["images"])
        return all_images


def scan_dataset(dataset_path: str) -> DatasetProfile:
    """便捷函数：扫描数据集"""
    scanner = DatasetScanner(dataset_path)
    return scanner.scan()


def discover_datasets(base_dir: str) -> List[DatasetProfile]:
    """发现目录下的所有数据集"""
    base_path = Path(base_dir)
    datasets = []

    if not base_path.exists():
        return datasets

    for item in base_path.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            try:
                profile = scan_dataset(str(item))
                if profile.image_count > 0:
                    datasets.append(profile)
            except Exception as e:
                logger.warning(f"扫描数据集失败 {item}: {e}")

    return datasets
