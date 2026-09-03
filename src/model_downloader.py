"""
模型下载工具（阶段 C5）

``ensure_model()`` 检查 ``basemodels/<file>.pt`` 是否存在，不存在则触发 Ultralytics
下载（YOLO 第一次构造时会自动从 GitHub 下载权重到当前缓存）。

设计原则：
- 不替代 Ultralytics 自己的下载机制——只是把它包装成幂等函数
- 下载失败时给出明确错误（网络 / 权限 / 磁盘）
- 支持本地手动放置（用户从国内镜像下载后放 basemodels/）

示例：
    from src.model_downloader import ensure_model
    path = ensure_model("yolov8n.pt", base_dir)
    # path == "basemodels/yolov8n.pt"（已存在或下载成功）
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def get_model_path(filename: str, base_dir: Path | str) -> Path:
    """返回 basemodels/ 下某文件的绝对路径（不检查是否存在）。"""
    return Path(base_dir) / "basemodels" / filename


def is_model_downloaded(filename: str, base_dir: Path | str) -> bool:
    """检查模型是否已下载到 basemodels/。"""
    return get_model_path(filename, base_dir).exists()


def move_cached_model(filename: str, base_dir: Path | str) -> Path | None:
    """Ultralytics 默认缓存到 ~/.../weights/ 或项目 Ultralytics/。

    本函数扫描这些位置，若找到 ``<filename>```` 则移动到 ``basemodels/``。
    Returns:
        移动后的本地路径；未找到时返回 None。
    """
    candidates: list[Path] = [
        Path(base_dir) / "Ultralytics" / "weights" / filename,
        Path(base_dir) / ".ci" / "ultralytics" / "weights" / filename,
    ]
    home = Path.home()
    candidates.append(home / ".config" / "Ultralytics" / "weights" / filename)
    # Windows
    if home is not None:
        appdata = home / "AppData" / "Local" / "Ultralytics" / "weights" / filename
        candidates.append(appdata)

    target = get_model_path(filename, base_dir)
    for src in candidates:
        if src.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(src), str(target))
                logger.info("Moved cached model %s → %s", src, target)
                return target
            except Exception as e:
                logger.warning("Failed to move %s → %s: %s", src, target, e)
                continue
    return None


def ensure_model(filename: str, base_dir: Path | str) -> Path:
    """确保指定模型文件已下载到 basemodels/。

    流程：
    1. 检查 basemodels/<file>.pt 是否存在 → 是则返回
    2. 检查 Ultralytics 缓存位置 → 若有则 move 到 basemodels/
    3. 触发 YOLO() 构造 → Ultralytics 会自动下载到缓存目录
    4. 再次扫描缓存并 move 到 basemodels/

    Args:
        filename: 模型文件名（如 ``"yolov8n.pt"``）
        base_dir: 项目根目录

    Returns:
        本地路径（绝对路径）

    Raises:
        FileNotFoundError: 下载失败（网络/权限/磁盘问题）
    """
    target = get_model_path(filename, base_dir)

    # 1. 已存在
    if target.exists():
        logger.info("Model already exists: %s", target)
        return target

    # 2. 缓存可能已有（之前的 Ultralytics 下载）
    moved = move_cached_model(filename, base_dir)
    if moved is not None:
        return moved

    # 3. 触发下载（Ultralytics 在构造时检查本地，缺失则下载）
    try:
        from ultralytics import YOLO

        logger.info("Triggering Ultralytics download for: %s", filename)
        # 只构造不训练——触发权重下载
        YOLO(filename)
    except ImportError as e:
        raise FileNotFoundError(
            f"Ultralytics not installed; cannot auto-download. "
            f"Please manually place {filename} at {target}"
        ) from e
    except Exception as e:
        raise FileNotFoundError(
            f"Failed to download {filename}: {e}. "
            f"Please manually place the file at {target}."
        ) from e

    # 4. 再次扫描缓存
    moved = move_cached_model(filename, base_dir)
    if moved is not None:
        return moved

    # 5. 最后兜底：返回目标路径（让用户知道去哪里找）
    raise FileNotFoundError(
        f"After download, {filename} not found in Ultralytics cache. "
        f"Expected at {target}. Please check ~/.config/Ultralytics/weights/."
    )


__all__ = [
    "ensure_model",
    "get_model_path",
    "is_model_downloaded",
    "move_cached_model",
]
