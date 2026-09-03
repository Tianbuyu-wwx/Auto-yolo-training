"""
训练报告产物解析（阶段 C7）

Ultralytics 在 ``runs/<run>/`` 目录下生成多种可视化文件：

- ``results.png`` / ``results.csv`` — 训练曲线（loss/mAP over epochs）
- ``confusion_matrix_normalized.png`` — 类别混淆矩阵
- ``BoxP_curve.png`` / ``BoxR_curve.png`` / ``BoxF1_curve.png`` — P/R/F1 曲线
- ``val_batch0_pred.jpg`` 等 — 验证集可视化

本模块提供：
- ``list_run_artifacts(run_dir)`` — 列出某次训练产出的所有有用文件
- ``parse_results_csv(run_dir)`` — 解析 results.csv 为 pandas DataFrame
- ``find_latest_run(dataset_name, base_dir)`` — 找最新训练运行目录

设计原则：只读取不修改产物文件；缺失文件返回空/None 而非抛错。
"""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


# 任务无关的核心产物（所有任务都有）
COMMON_ARTIFACTS = [
    "results.png",
    "results.csv",
]

# 检测任务的额外产物
DETECT_ARTIFACTS = [
    "confusion_matrix_normalized.png",
    "BoxP_curve.png",
    "BoxR_curve.png",
    "BoxF1_curve.png",
    "P_curve.png",
    "R_curve.png",
    "F1_curve.png",
]

# 训练曲线图像（用于 Gradio 展示）
TRAINING_PLOT_ARTIFACTS = [
    "results.png",
    "BoxP_curve.png",
    "BoxR_curve.png",
    "BoxF1_curve.png",
    "confusion_matrix_normalized.png",
]


@dataclass(frozen=True)
class RunArtifacts:
    """一次训练产出的所有可视化文件路径。"""

    run_dir: Path
    csv_path: Path | None
    plots: list[Path]  # PNG 文件（用于 Gradio Gallery 显示）

    @property
    def has_results_csv(self) -> bool:
        return self.csv_path is not None and self.csv_path.exists()


def find_latest_run(dataset_name: str, base_dir: Path | str) -> Path | None:
    """查找 ``runs/detect/<dataset>_*`` 最新一次训练运行目录。

    Ultralytics 自动命名：``runs/detect/<name>`` → 若已存在则 ``<name>2`` → ``<name>3``。
    """
    runs_dir = Path(base_dir) / "runs" / "detect"
    if not runs_dir.exists():
        return None
    candidates: list[tuple[float, Path]] = []
    for entry in runs_dir.iterdir():
        if not entry.is_dir():
            continue
        if dataset_name not in entry.name:
            continue
        try:
            mtime = entry.stat().st_mtime
            candidates.append((mtime, entry))
        except OSError:
            continue
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def list_run_artifacts(run_dir: Path | str) -> RunArtifacts:
    """列出一次训练产出的核心可视化资源。"""
    run_path = Path(run_dir)
    csv_path = run_path / "results.csv"
    plots: list[Path] = []
    for name in TRAINING_PLOT_ARTIFACTS:
        p = run_path / name
        if p.exists():
            plots.append(p)
    return RunArtifacts(
        run_dir=run_path,
        csv_path=csv_path if csv_path.exists() else None,
        plots=plots,
    )


def parse_results_csv(run_dir: Path | str) -> list[dict]:
    """解析 ``results.csv`` 为 list of dict。

    Args:
        run_dir: 训练运行目录（含 results.csv）

    Returns:
        每个 epoch 一条记录；文件不存在返回空列表
    """
    csv_path = Path(run_dir) / "results.csv"
    if not csv_path.exists():
        return []
    out: list[dict] = []
    try:
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # 去掉可能的空格键
                cleaned = {k.strip(): v.strip() if isinstance(v, str) else v for k, v in row.items()}
                out.append(cleaned)
    except Exception as e:
        logger.warning("Failed to parse results.csv: %s", e)
    return out


__all__ = [
    "COMMON_ARTIFACTS",
    "DETECT_ARTIFACTS",
    "RunArtifacts",
    "TRAINING_PLOT_ARTIFACTS",
    "find_latest_run",
    "list_run_artifacts",
    "parse_results_csv",
]
