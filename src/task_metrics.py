"""
任务感知的评估指标（阶段 C6）

Ultralytics 不同任务的指标键不同：
- detect:    metrics/mAP50(B) / metrics/mAP50-95(B) / metrics/precision(B) / metrics/recall(B)
- segment:   metrics/mAP50(M) / metrics/mAP50-95(M) / metrics/precision(M) / metrics/recall(M)
- pose:      metrics/mAP50(P) / metrics/mAP50-95(P)
- classify:  metrics/accuracy_top1 / metrics/accuracy_top5

本模块提供：
- ``task_metrics_keys(task)``: 返回该任务下应提取的指标键列表
- ``extract_task_metrics(results, task)``: 从 Ultralytics val 结果字典提取指标
- ``task_metric_label(key)``: 把指标键转为人类可读标签（如 "mAP50(B)" → "mAP@50"）

设计原则：不做跨任务标注转换（不可行），只做评估指标键的统一接口。
"""
from __future__ import annotations

from typing import Any

from src.task_types import TaskType, get_task_spec

# 各任务的指标键后缀（Ultralytics 输出 keys）
TASK_METRICS: dict[TaskType, list[str]] = {
    TaskType.DETECT: [
        "metrics/mAP50(B)",
        "metrics/mAP50-95(B)",
        "metrics/precision(B)",
        "metrics/recall(B)",
    ],
    TaskType.SEGMENT: [
        "metrics/mAP50(M)",
        "metrics/mAP50-95(M)",
        "metrics/precision(M)",
        "metrics/recall(M)",
    ],
    TaskType.POSE: [
        "metrics/mAP50(P)",
        "metrics/mAP50-95(P)",
    ],
    TaskType.CLASSIFY: [
        "metrics/accuracy_top1",
        "metrics/accuracy_top5",
    ],
    TaskType.OBB: [
        "metrics/mAP50(B)",
        "metrics/mAP50-95(B)",
    ],
}


# 指标键 → 人类可读标签
_METRIC_LABELS: dict[str, str] = {
    "metrics/mAP50(B)": "mAP@50",
    "metrics/mAP50-95(B)": "mAP@50-95",
    "metrics/precision(B)": "Precision",
    "metrics/recall(B)": "Recall",
    "metrics/mAP50(M)": "mAP@50 (Mask)",
    "metrics/mAP50-95(M)": "mAP@50-95 (Mask)",
    "metrics/precision(M)": "Precision (Mask)",
    "metrics/recall(M)": "Recall (Mask)",
    "metrics/mAP50(P)": "mAP@50 (Pose)",
    "metrics/mAP50-95(P)": "mAP@50-95 (Pose)",
    "metrics/accuracy_top1": "Accuracy@1",
    "metrics/accuracy_top5": "Accuracy@5",
}


def task_metrics_keys(task: TaskType | str) -> list[str]:
    """返回指定任务应提取的指标键列表。"""
    spec_task = get_task_spec(task).task if isinstance(task, str) else task
    return list(TASK_METRICS.get(spec_task, []))


def task_metric_label(key: str) -> str:
    """把 Ultralytics 指标键转为人类可读标签。未知键返回原键。"""
    return _METRIC_LABELS.get(key, key)


def extract_task_metrics(results: Any, task: TaskType | str) -> dict[str, float]:
    """从 Ultralytics val 结果提取该任务的指标。

    支持 results.results_dict / results.metrics（dict 形式）。

    Args:
        results: Ultralytics YOLO.val() 返回值
        task: 任务类型

    Returns:
        ``{label: float}`` 字典（如 ``{"mAP@50": 0.85, "mAP@50-95": 0.42}``）
    """
    raw: dict[str, Any] = {}
    if hasattr(results, "results_dict"):
        raw = dict(results.results_dict or {})
    elif hasattr(results, "metrics"):
        m = results.metrics
        if isinstance(m, dict):
            raw = m

    out: dict[str, float] = {}
    for key in task_metrics_keys(task):
        if key in raw:
            try:
                out[task_metric_label(key)] = float(raw[key])
            except (TypeError, ValueError):
                continue
    return out


__all__ = [
    "TASK_METRICS",
    "extract_task_metrics",
    "task_metric_label",
    "task_metrics_keys",
]
