"""
公共工具函数
消除各模块间的重复代码
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from src.constants import (
    BASEMODELS_DIR,
    PROJECT_ROOT,
    SUPPORTED_IMAGE_EXTS,
)


def imread_unicode(path: str, flags: int = cv2.IMREAD_UNCHANGED) -> np.ndarray | None:
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
    allowed_dirs: list[str],
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


def find_images(directory: Path, recursive: bool = True) -> list[Path]:
    """查找目录中的所有图像文件"""
    if not directory.exists():
        return []
    glob_fn = directory.rglob if recursive else directory.glob
    return sorted([f for f in glob_fn("*") if f.suffix.lower() in SUPPORTED_IMAGE_EXTS and f.is_file()])


logger = logging.getLogger(__name__)


def recycle_path(path: Path, recycle_root: Path) -> Path | None:
    """把文件/目录移入回收站（`<recycle_root>/<原名>_<时间戳>`），返回新路径。

    训练产物、数据集这类东西一旦 ``shutil.rmtree`` 就不可恢复，而控制台上一次
    误点就足以触发。项目统一约定：**清理 = 移走，不是抹掉** —— `dataset/.recycle`
    与 `runs/.recycle` 都是这个思路，用户想彻底清空时自行删回收目录即可。

    同名目标已存在时追加 ``_2``、``_3``……；任何 OSError 只记日志并返回 ``None``，
    让调用方知道「回收失败」而不是让清理动作把主流程带崩。
    """
    source = Path(path)
    if not source.exists():
        return None
    try:
        recycle_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = recycle_root / f"{source.name}_{stamp}"
        seq = 2
        while dest.exists():
            dest = recycle_root / f"{source.name}_{stamp}_{seq}"
            seq += 1
        shutil.move(str(source), str(dest))
        return dest
    except OSError as exc:
        logger.warning("[RECYCLE] 移入回收站失败 %s: %s", source, exc)
        return None


def is_tensorboard_available() -> bool:
    """检测 TensorBoard 是否可用（P3-3：Ultralytics 检测到后自动记录训练曲线）

    可用后运行 `tensorboard --logdir runs` 即可查看所有训练的可视化。
    """
    try:
        import tensorboard  # noqa: F401
        return True
    except ImportError:
        return False
