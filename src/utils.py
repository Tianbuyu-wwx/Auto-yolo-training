"""
公共工具函数
消除各模块间的重复代码
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Optional, List

from src.constants import BASEMODELS_DIR, SUPPORTED_IMAGE_EXTS, ALLOWED_IMAGE_DIRS, ALLOWED_MODEL_DIRS, PROJECT_ROOT


def imread_unicode(path: str, flags: int = cv2.IMREAD_UNCHANGED) -> Optional[np.ndarray]:
    """
    支持中文路径的图像读取函数
    OpenCV的cv2.imread在Windows上不支持中文路径，使用np.fromfile绕过此限制
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        img_array = np.fromfile(path, np.uint8)
        img = cv2.imdecode(img_array, flags)
        if img is not None:
            return img
    except Exception as e:
        logger.debug("[imread_unicode] np.fromfile 读取失败 %s: %s", path, e)

    try:
        img = cv2.imread(path, flags)
        if img is not None:
            return img
    except Exception as e:
        logger.debug("[imread_unicode] cv2.imread 读取失败 %s: %s", path, e)

    return None


def resolve_model_path(model: str, basemodels_dir: Path = BASEMODELS_DIR) -> str:
    """
    解析模型路径。
    如果传入的是文件名（如 yolov8s.pt），优先从 basemodels/ 目录查找；
    如果传入的是完整路径，则直接使用。
    """
    if not model:
        return model
    model_path = Path(model)
    if model_path.is_absolute() or len(model_path.parts) > 1:
        return str(model_path)
    if basemodels_dir.exists():
        candidate = basemodels_dir / model
        if candidate.exists():
            return str(candidate)
    return model


def is_path_allowed(
    path: str,
    allowed_dirs: List[str],
    base_dir: Path = PROJECT_ROOT,
) -> bool:
    """
    检查给定路径是否位于允许的目录下，防止路径穿越。

    Args:
        path: 待检查路径
        allowed_dirs: 允许的相对目录列表
        base_dir: 基准目录（项目根目录）

    Returns:
        True 表示路径合法且在白名单目录下
    """
    if not path:
        return False
    try:
        target = Path(path).resolve()
        for allowed in allowed_dirs:
            allowed_path = (base_dir / allowed).resolve()
            try:
                target.relative_to(allowed_path)
                return True
            except ValueError:
                continue
        return False
    except Exception:
        return False


def count_images(directory: Path, recursive: bool = True) -> int:
    """统计目录中的图像文件数量"""
    if not directory.exists():
        return 0
    glob_fn = directory.rglob if recursive else directory.glob
    return sum(1 for f in glob_fn("*") if f.suffix.lower() in SUPPORTED_IMAGE_EXTS and f.is_file())


def find_images(directory: Path, recursive: bool = True) -> List[Path]:
    """查找目录中的所有图像文件"""
    if not directory.exists():
        return []
    glob_fn = directory.rglob if recursive else directory.glob
    return sorted([f for f in glob_fn("*") if f.suffix.lower() in SUPPORTED_IMAGE_EXTS and f.is_file()])
