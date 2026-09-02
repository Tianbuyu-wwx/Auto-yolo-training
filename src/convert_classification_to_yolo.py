"""
图像分类数据集转YOLO格式工具
将按类别子目录组织的分类数据集转换为YOLO目标检测格式
"""

import shutil
from pathlib import Path
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)


def convert_classification_to_yolo(
    src_dir: str,
    dest_dir: str,
    class_names: List[str] = None,
    splits: List[str] = None,
) -> Dict[str, int]:
    """
    将分类数据集转换为YOLO格式
    
    Args:
        src_dir: 源数据集路径（包含 images/{split}/{class}/ 结构）
        dest_dir: 目标数据集路径（将创建 images/{split}/ + labels/{split}/ 结构）
        class_names: 类别名称列表（如果为None，自动从目录名推断）
        splits: 数据集分割列表，默认 ["train", "val", "test"]
        
    Returns:
        统计信息字典 {split: image_count}
    """
    src_path = Path(src_dir)
    dest_path = Path(dest_dir)
    
    if splits is None:
        splits = ["train", "val", "test"]
    
    stats = {}
    images_dir = src_path / "images"
    
    # 支持两种结构：
    # 1. images/{split}/{class}/ （带images包装）
    # 2. {split}/{class}/ （无images包装）
    has_images_wrapper = images_dir.exists()
    
    if not has_images_wrapper:
        # 验证是否有直接的split目录
        has_split = any((src_path / split).exists() for split in splits)
        if not has_split:
            raise ValueError(f"源数据集不包含有效的分类数据集结构: {src_path}")
        logger.info("[CONVERT] 检测到无images包装的分类数据集结构: %s", src_path)
    
    # 自动检测类别（如果未提供）
    if class_names is None:
        # 从所有split的子目录中收集类别名
        all_classes = set()
        for split in splits:
            if has_images_wrapper:
                split_dir = images_dir / split
            else:
                split_dir = src_path / split
            
            if split_dir.exists():
                for d in split_dir.iterdir():
                    if d.is_dir() and not d.name.startswith("."):
                        all_classes.add(d.name)
        
        if all_classes:
            class_names = sorted(list(all_classes))
    
    if not class_names:
        raise ValueError("无法确定类别名称，请手动提供 class_names 参数")
    
    class_to_id = {name: i for i, name in enumerate(class_names)}
    
    # 清理目标目录
    if dest_path.exists():
        shutil.rmtree(dest_path)
    
    for split in splits:
        if has_images_wrapper:
            src_split_dir = images_dir / split
        else:
            src_split_dir = src_path / split
            
        if not src_split_dir.exists():
            continue
        
        dest_images_split = dest_path / "images" / split
        dest_labels_split = dest_path / "labels" / split
        dest_images_split.mkdir(parents=True, exist_ok=True)
        dest_labels_split.mkdir(parents=True, exist_ok=True)
        
        image_count = 0
        
        for class_name, class_id in class_to_id.items():
            src_class_dir = src_split_dir / class_name
            if not src_class_dir.exists():
                continue
            
            # 复制图像并创建标注文件
            for img_file in src_class_dir.iterdir():
                if not img_file.is_file():
                    continue
                
                # 支持的图像格式
                if img_file.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif", ".tiff"}:
                    continue
                
                # 复制图像到目标目录
                dest_img = dest_images_split / img_file.name
                
                # 处理文件名冲突
                if dest_img.exists():
                    dest_img = dest_images_split / f"{class_name}_{img_file.name}"
                
                shutil.copy2(str(img_file), str(dest_img))
                
                # 创建YOLO标注文件（全图作为目标）
                # 格式: class_id x_center y_center width height
                # x_center, y_center, width, height 都是相对坐标 (0-1)
                label_file = dest_labels_split / f"{dest_img.stem}.txt"
                with open(label_file, "w", encoding="utf-8") as f:
                    # 全图目标：中心(0.5, 0.5)，宽高(1.0, 1.0)
                    f.write(f"{class_id} 0.5 0.5 1.0 1.0\n")
                
                image_count += 1
        
        stats[split] = image_count
    
    # 创建 data.yaml 文件
    data_yaml_path = dest_path / "data.yaml"
    with open(data_yaml_path, "w", encoding="utf-8") as f:
        f.write(f"# 自动生成的YOLO数据集配置\n")
        f.write(f"# 源数据: {src_path}\n")
        f.write(f"train: ../images/train\n")
        f.write(f"val: ../images/val\n")
        if "test" in stats:
            f.write(f"test: ../images/test\n")
        f.write(f"\n")
        f.write(f"nc: {len(class_names)}\n")
        f.write(f"names: {class_names}\n")
    
    return stats


if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    
    if len(sys.argv) < 3:
        print("用法: python convert_classification_to_yolo.py <源数据集路径> <目标数据集路径>")
        print("示例: python convert_classification_to_yolo.py 'dataset/cable end sleeve' 'dataset/cable-end-sleeve-yolo'")
        sys.exit(1)
    
    src = sys.argv[1]
    dest = sys.argv[2]
    
    print(f"源数据集: {src}")
    print(f"目标数据集: {dest}")
    print()
    
    stats = convert_classification_to_yolo(src, dest)
    
    print("\n转换统计:")
    for split, count in stats.items():
        print(f"  {split}: {count} 张图像")
    print(f"  总计: {sum(stats.values())} 张图像")
