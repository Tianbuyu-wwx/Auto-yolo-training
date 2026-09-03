"""
模型清单（阶段 C2 + C3）

提供：
- ``ModelFamily`` 枚举（yolov5/yolov8/yolov11/yolo26）+ 从文件名推断
- ``MODEL_CATALOG`` 字典：每个模型家族的可用预训练权重清单
- ``resolve_model_family()``：根据文件名判断家族
- ``check_local_models()``：扫描 basemodels/ + 报告缺失
- ``suggest_download()``：返回缺失模型的下载命令

设计原则：
- 不强行下载：只提示用户，由 ``serve.py`` / ``gradio_app.py`` / ``train.py`` 暴露提示
- 不绑定具体业务场景：所有 Ultralytics 官方支持的模型家族都覆盖
- 单文件无依赖：方便未来扩展其他任务类型（segment/pose/classify）
"""
from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

logger = logging.getLogger(__name__)


class ModelFamily(StrEnum):
    """支持的 YOLO 模型家族（按 Ultralytics 8.4 命名约定）。"""

    YOLOV5 = "yolov5"
    YOLOV8 = "yolov8"
    YOLOV11 = "yolov11"
    YOLO26 = "yolo26"
    UNKNOWN = "unknown"


# 文件名前缀 → 家族（按 ultralytics 官方命名）
_FAMILY_PREFIXES = {
    "yolov5": ModelFamily.YOLOV5,
    "yolov8": ModelFamily.YOLOV8,
    "yolo11": ModelFamily.YOLOV11,
    "yolo26": ModelFamily.YOLO26,
}


def resolve_model_family(filename: str | Path) -> ModelFamily:
    """根据文件名推断模型家族。

    Examples:
        "yolov8s.pt" → ModelFamily.YOLOV8
        "yolo11n-seg.pt" → ModelFamily.YOLOV11
        "yolo26m.pt" → ModelFamily.YOLO26
        "custom_model.pt" → ModelFamily.UNKNOWN
    """
    name = Path(filename).stem.lower()
    for prefix, family in _FAMILY_PREFIXES.items():
        if name.startswith(prefix):
            return family
    return ModelFamily.UNKNOWN


@dataclass(frozen=True)
class ModelEntry:
    """预训练模型条目。"""

    filename: str
    family: ModelFamily
    size: str  # n/s/m/l/x
    task: str = "detect"  # detect/segment/pose/classify
    size_mb: float | None = None  # 已知文件大小（MB），None 表示未下载

    @property
    def download_url(self) -> str:
        """Ultralytics 自动下载 URL（首次使用时按需下载）。"""
        return f"https://github.com/ultralytics/assets/releases/download/v8.4.0/{self.filename}"


# 预训练模型清单（Ultralytics 8.4 官方）
MODEL_CATALOG: dict[str, ModelEntry] = {
    # YOLOv5
    "yolov5n.pt": ModelEntry("yolov5n.pt", ModelFamily.YOLOV5, "n"),
    "yolov5s.pt": ModelEntry("yolov5s.pt", ModelFamily.YOLOV5, "s"),
    "yolov5m.pt": ModelEntry("yolov5m.pt", ModelFamily.YOLOV5, "m"),
    # YOLOv8
    "yolov8n.pt": ModelEntry("yolov8n.pt", ModelFamily.YOLOV8, "n"),
    "yolov8s.pt": ModelEntry("yolov8s.pt", ModelFamily.YOLOV8, "s"),
    "yolov8m.pt": ModelEntry("yolov8m.pt", ModelFamily.YOLOV8, "m"),
    "yolov8l.pt": ModelEntry("yolov8l.pt", ModelFamily.YOLOV8, "l"),
    "yolov8x.pt": ModelEntry("yolov8x.pt", ModelFamily.YOLOV8, "x"),
    # YOLOv8 segment
    "yolov8n-seg.pt": ModelEntry("yolov8n-seg.pt", ModelFamily.YOLOV8, "n", task="segment"),
    "yolov8s-seg.pt": ModelEntry("yolov8s-seg.pt", ModelFamily.YOLOV8, "s", task="segment"),
    "yolov8m-seg.pt": ModelEntry("yolov8m-seg.pt", ModelFamily.YOLOV8, "m", task="segment"),
    # YOLOv8 pose
    "yolov8n-pose.pt": ModelEntry("yolov8n-pose.pt", ModelFamily.YOLOV8, "n", task="pose"),
    "yolov8s-pose.pt": ModelEntry("yolov8s-pose.pt", ModelFamily.YOLOV8, "s", task="pose"),
    "yolov8m-pose.pt": ModelEntry("yolov8m-pose.pt", ModelFamily.YOLOV8, "m", task="pose"),
    # YOLOv8 classify
    "yolov8n-cls.pt": ModelEntry("yolov8n-cls.pt", ModelFamily.YOLOV8, "n", task="classify"),
    "yolov8s-cls.pt": ModelEntry("yolov8s-cls.pt", ModelFamily.YOLOV8, "s", task="classify"),
    "yolov8m-cls.pt": ModelEntry("yolov8m-cls.pt", ModelFamily.YOLOV8, "m", task="classify"),
    # YOLOv11
    "yolo11n.pt": ModelEntry("yolo11n.pt", ModelFamily.YOLOV11, "n"),
    "yolo11s.pt": ModelEntry("yolo11s.pt", ModelFamily.YOLOV11, "s"),
    "yolo11m.pt": ModelEntry("yolo11m.pt", ModelFamily.YOLOV11, "m"),
    "yolo11l.pt": ModelEntry("yolo11l.pt", ModelFamily.YOLOV11, "l"),
    "yolo11x.pt": ModelEntry("yolo11x.pt", ModelFamily.YOLOV11, "x"),
    # YOLO26
    "yolo26n.pt": ModelEntry("yolo26n.pt", ModelFamily.YOLO26, "n"),
    "yolo26s.pt": ModelEntry("yolo26s.pt", ModelFamily.YOLO26, "s"),
    "yolo26m.pt": ModelEntry("yolo26m.pt", ModelFamily.YOLO26, "m"),
    "yolo26l.pt": ModelEntry("yolo26l.pt", ModelFamily.YOLO26, "l"),
    "yolo26x.pt": ModelEntry("yolo26x.pt", ModelFamily.YOLO26, "x"),
}


@dataclass
class LocalModelStatus:
    """本地模型清单状态。"""

    available: list[Path]
    missing_popular: list[ModelEntry]
    total_size_mb: float

    def summary(self) -> dict:
        """返回易于打印的字典。"""
        return {
            "available_count": len(self.available),
            "available_files": [p.name for p in self.available],
            "missing_popular_count": len(self.missing_popular),
            "missing_popular": [
                {"filename": e.filename, "family": e.family.value, "task": e.task}
                for e in self.missing_popular
            ],
            "total_size_mb": round(self.total_size_mb, 2),
        }


def check_local_models(
    basemodels_dir: Path | str,
    *,
    include_sizes: list[str] | None = None,
) -> LocalModelStatus:
    """扫描 basemodels/ 目录，报告本地可用 + 缺失的流行模型。

    Args:
        basemodels_dir: 预训练模型存放目录（通常为 basemodels/）
        include_sizes: 关心哪些 size（默认 ["n", "s"]——最常用的两个）。
                       例如 ["n", "s", "m"] 会扩展检查范围。

    Returns:
        ``LocalModelStatus`` 包含 available / missing_popular / total_size_mb
    """
    if include_sizes is None:
        include_sizes = ["n", "s"]

    basemodels_dir = Path(basemodels_dir)
    available: list[Path] = []
    total_size = 0.0

    if basemodels_dir.exists():
        for pt_file in sorted(basemodels_dir.glob("*.pt")):
            available.append(pt_file)
            with contextlib.suppress(OSError):
                total_size += pt_file.stat().st_size / (1024 * 1024)

    # 检查"流行"模型（用户最常用 n/s 系列）
    missing_popular: list[ModelEntry] = []
    for entry in MODEL_CATALOG.values():
        if entry.size not in include_sizes:
            continue
        if not (basemodels_dir / entry.filename).exists():
            missing_popular.append(entry)

    return LocalModelStatus(
        available=available,
        missing_popular=missing_popular,
        total_size_mb=total_size,
    )


def suggest_download(entries: list[ModelEntry], basemodels_dir: Path | str | None = None) -> list[str]:
    """返回下载命令列表（用户可在终端直接执行）。

    Args:
        entries: 缺失的模型条目列表
        basemodels_dir: 目标目录（默认 basemodels/）

    Returns:
        可在 bash/PowerShell 直接运行的命令列表（每行一条命令，含注释）
    """
    basemodels_dir = Path(basemodels_dir or "basemodels")
    basemodels_dir.mkdir(parents=True, exist_ok=True)
    commands: list[str] = []
    for e in entries:
        commands.append(f"# 下载 {e.filename}（{e.family.value} {e.size}, {e.task}）")
        commands.append(f"curl -L -o {basemodels_dir / e.filename} {e.download_url}")
        commands.append("")
    return commands


def model_filename_to_family_dict(filenames: list[str]) -> dict[str, ModelFamily]:
    """批量推断家族（供 UI dropdown 使用）。"""
    return {name: resolve_model_family(name) for name in filenames}


__all__ = [
    "MODEL_CATALOG",
    "LocalModelStatus",
    "ModelEntry",
    "ModelFamily",
    "check_local_models",
    "model_filename_to_family_dict",
    "resolve_model_family",
    "suggest_download",
]
