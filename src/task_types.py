"""
任务类型抽象（阶段 C1）。

Ultralytics 支持 5 大任务：检测 (detect) / 分割 (segment) / 姿态估计 (pose) /
分类 (classify) / OBB 定向检测 (obb)。本模块定义统一抽象，便于：
1. ``TrainConfig`` 接受 ``task`` 字段，传递给 Ultralytics
2. ``InferenceService`` 根据 task 调整响应字段（detect=box，classify=top-k）
3. 未来扩展新任务（OBB 等）只加一个枚举值

设计原则：
- ``TaskType`` 与 Ultralytics YOLO 字段名严格对齐（如 ``"detect"``、``"segment"``）
- 不重新定义模型架构——Ultralytics 已经覆盖
- ``TaskSpec`` 提供每种任务的专属配置（如 detect 默认 imgsz=640，classify 用 224）
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TaskType(StrEnum):
    """Ultralytics 任务类型枚举（字符串值兼容 ultralytics.YOLO(task=...)）。"""

    DETECT = "detect"        # 目标检测：bbox
    SEGMENT = "segment"      # 实例分割：polygon
    POSE = "pose"           # 姿态估计：keypoints
    CLASSIFY = "classify"    # 图像分类：top-k 类别
    OBB = "obb"             # 定向检测：旋转 bbox（阶段 C1 占位）


@dataclass(frozen=True)
class TaskSpec:
    """每种任务的专属配置（imgsz / label format / 默认模型）。"""

    task: TaskType
    default_imgsz: int
    default_model_suffix: str  # 如 yolov8n / yolo11n / yolo26n
    label_format: str         # 人类可读的标注格式
    description: str

    @property
    def supports_bbox(self) -> bool:
        return self.task in (TaskType.DETECT, TaskType.SEGMENT, TaskType.OBB)

    @property
    def supports_keypoints(self) -> bool:
        return self.task == TaskType.POSE


# 阶段 C1：4 大主流任务的默认配置（参考 Ultralytics 官方文档）
TASK_SPECS: dict[TaskType, TaskSpec] = {
    TaskType.DETECT: TaskSpec(
        task=TaskType.DETECT,
        default_imgsz=640,
        default_model_suffix="yolov8n",
        label_format="YOLO bbox: class_id x_center y_center width height (normalized 0-1)",
        description="目标检测：每个对象一个边界框 + 类别",
    ),
    TaskType.SEGMENT: TaskSpec(
        task=TaskType.SEGMENT,
        default_imgsz=640,
        default_model_suffix="yolov8n-seg",
        label_format="YOLO seg: class_id x1 y1 x2 y2 ... xn yn (normalized 0-1)",
        description="实例分割：每个对象一个像素级多边形 + 类别",
    ),
    TaskType.POSE: TaskSpec(
        task=TaskType.POSE,
        default_imgsz=640,
        default_model_suffix="yolov8n-pose",
        label_format="YOLO pose: class_id x1 y1 v1 x2 y2 v2 ... (17 keypoints for COCO)",
        description="姿态估计：人体/物体关键点 + 类别",
    ),
    TaskType.CLASSIFY: TaskSpec(
        task=TaskType.CLASSIFY,
        default_imgsz=224,
        default_model_suffix="yolov8n-cls",
        label_format="ImageFolder classification: subdirectory name = class name",
        description="图像分类：整张图 → 单一类别标签（无需标注文件）",
    ),
    TaskType.OBB: TaskSpec(
        task=TaskType.OBB,
        default_imgsz=640,
        default_model_suffix="yolov8n-obb",
        label_format="YOLO OBB: class_id x1 y1 x2 y2 x3 y3 x4 y4 (normalized 0-1)",
        description="定向检测：旋转边框（遥感/航空图像常用）",
    ),
}


def get_task_spec(task: TaskType | str) -> TaskSpec:
    """获取任务配置（支持字符串转换）。

    Args:
        task: TaskType 枚举或字符串（"detect"/"segment"/"pose"/"classify"/"obb"）

    Returns:
        TaskSpec 实例

    Raises:
        ValueError: 不支持的任务类型
    """
    if isinstance(task, str):
        try:
            task = TaskType(task)
        except ValueError as e:
            valid = ", ".join(t.value for t in TaskType)
            raise ValueError(
                f"不支持的任务类型: {task!r}。合法值: {valid}"
            ) from e
    return TASK_SPECS[task]


def model_name_for_task(task: TaskType | str, size: str = "n") -> str:
    """构造任务对应的模型文件名。

    示例：
        model_name_for_task("detect", "n")  → "yolov8n.pt"
        model_name_for_task("segment", "s") → "yolov8s-seg.pt"
        model_name_for_task("classify", "m") → "yolov8m-cls.pt"
        model_name_for_task("pose", "l")   → "yolov8l-pose.pt"
    """
    spec = get_task_spec(task)
    suffix = spec.default_model_suffix

    # 默认 suffix 已含 size：yolov8n / yolov8n-seg / yolov8n-cls 等
    # 调用方传 size 时重写：
    # "yolov8{n}-{sub}" 模式：分离 main 和 sub
    parts = suffix.split("-", 1)
    main_part = parts[0]  # "yolov8n"
    sub_part = parts[1] if len(parts) > 1 else ""  # "seg" / "cls" / "pose" / "obb"

    # 重写 size: yolov8n → yolov8{s}
    main_with_new_size = main_part[:-1] + size

    if sub_part:
        return f"{main_with_new_size}-{sub_part}.pt"
    return f"{main_with_new_size}.pt"


__all__ = [
    "TASK_SPECS",
    "TaskSpec",
    "TaskType",
    "get_task_spec",
    "model_name_for_task",
]
