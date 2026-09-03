"""
训练流水线阶段实现（阶段 B7 拆分·保守版）。

从 src.training_pipeline 的 TrainingPipeline 类中**只**抽出最简单的 2 个
``_run_*`` 方法（``_run_validation`` 和 ``_run_export``）到独立模块。

设计决策（2026-09-03）：
- 完整拆分（5 个全部抽出）风险高：``_run_training`` 有 100+ 行 model 路径解析、
  GPU 探测、stop callback、run_dir 自动发现逻辑，与 TrainingPipeline 类状态耦合深。
- 阶段 C 再做完整拆分 + god class 重构。
- 现阶段保留 4 个阶段方法在类内，仅把最简单的 2 个外置，证明重构可行性。

约定：本模块函数是**无状态**的，所有依赖通过参数显式传入。
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from src.training_pipeline import PipelineResult

logger = logging.getLogger("TrainingPipeline.Stage")


# ----------------------------------------------------------------------
# Stage 1: 数据验证（最简单，纯函数）
# ----------------------------------------------------------------------
def run_validation(dataset_path: Path) -> PipelineResult:
    """执行数据验证。

    无状态实现：调用 ``validate_dataset``，把结果包装为 PipelineResult。
    不发通知（由 TrainingPipeline._run_validation 薄包装负责通知）。
    """
    start = time.time()

    from src.data_validator import validate_dataset

    report = validate_dataset(str(dataset_path))
    duration = time.time() - start

    if not report.is_valid:
        errors = report.get_errors()
        error_msgs = [f"[{e.category}] {e.message}" for e in errors[:5]]
        logger.error("  -> Validation found %d errors", len(errors))
        for err in errors[:5]:
            logger.error("     - [%s] %s (file: %s)", err.category, err.message, err.file_path or "N/A")
        return PipelineResult(
            success=False,
            stage="validation",
            message=f"数据验证失败，发现 {len(errors)} 个错误",
            duration=duration,
            details={
                "report": report.to_dict(),
                "error_samples": error_msgs,
            },
        )

    warnings = report.get_warnings()
    msg = "数据验证通过"
    if warnings:
        msg += f"，发现 {len(warnings)} 个警告"
        logger.warning("  -> Validation found %d warnings", len(warnings))
        for warn in warnings[:5]:
            logger.warning("     - [%s] %s", warn.category, warn.message)
    return PipelineResult(
        success=True,
        stage="validation",
        message=msg,
        duration=duration,
        details={"report": report.to_dict(), "stats": report.stats},
    )


# ----------------------------------------------------------------------
# Stage 5: 模型导出（较简单，外部 try/except + ModelExporter）
# ----------------------------------------------------------------------
def run_export(
    model_path: str,
    formats: list[str] | None = None,
    imgsz: int = 640,
    *,
    base_dir: Path,
    half: bool = False,
    int8: bool = False,
    dynamic: bool = True,
    simplify: bool = True,
    opset: int = 12,
    workspace: int = 4,
) -> PipelineResult:
    """执行模型导出。

    无状态实现：调用 ``ModelExporter.export``，把结果包装为 PipelineResult。
    """
    start = time.time()

    from src.model_exporter import ModelExporter

    exporter = ModelExporter(str(base_dir))
    try:
        report = exporter.export(
            model_path=model_path,
            formats=formats,
            imgsz=imgsz,
            half=half,
            int8=int8,
            dynamic=dynamic,
            simplify=simplify,
            opset=opset,
            workspace=workspace,
        )
        return PipelineResult(
            success=report.success_count > 0,
            stage="export",
            message=f"导出完成，成功 {report.success_count}/{report.total_count}",
            duration=time.time() - start,
            details={"export_report": report.to_dict()},
        )
    except Exception as e:
        return PipelineResult(
            success=False,
            stage="export",
            message=f"导出失败: {e}",
            duration=time.time() - start,
            error=str(e),
        )


__all__ = ["run_export", "run_validation"]
