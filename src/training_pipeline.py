"""
完整训练流水线框架
整合数据验证、配置生成、超参搜索、训练执行、评估、导出、通知
"""

import os
import sys
import json
import time
import gc
import logging
import traceback
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, Callable

from src.data_validator import validate_dataset, ValidationReport, Severity
from src.config_generator import ConfigGenerator, ProjectConfig, quick_setup
from src.hyperparameter_tuning import (
    YOLOHyperparameterTuner,
    SearchSpace,
    TuningResult,
)
from src.evaluator import ModelEvaluator, EvaluationReport
from src.model_exporter import ModelExporter, ExportReport
from src.notifier import NotifierManager, NotificationLevel, create_notifier


# 配置日志
logger = logging.getLogger("TrainingPipeline")
logger.setLevel(logging.INFO)

# 避免重复添加handler
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)


@dataclass
class PipelineResult:
    """流水线执行结果"""
    success: bool
    stage: str
    message: str
    duration: float
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class PipelineReport:
    """完整流水线报告"""
    dataset_name: str
    start_time: str
    end_time: Optional[str] = None
    total_duration: float = 0.0
    stages: list = field(default_factory=list)
    success: bool = False

    def add_stage(self, result: PipelineResult):
        self.stages.append({
            "stage": result.stage,
            "success": result.success,
            "message": result.message,
            "duration": result.duration,
            "details": self._serialize_value(result.details),
            "error": result.error,
        })

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "total_duration": self.total_duration,
            "success": self.success,
            "stages": self.stages,
        }

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        from dataclasses import is_dataclass, asdict
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, dict):
            return {k: PipelineReport._serialize_value(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [PipelineReport._serialize_value(v) for v in value]
        return value


class TrainingPipeline:
    """YOLO自动训练流水线"""

    def __init__(
        self,
        base_dir: Optional[str] = None,
        webhook_url: Optional[str] = None,
        webhook_type: str = "generic",
        max_backup_runs: int = 2,
        config_generator: Optional[ConfigGenerator] = None,
        evaluator: Optional[ModelEvaluator] = None,
        exporter: Optional[ModelExporter] = None,
        notifier: Optional[NotifierManager] = None,
    ):
        self.base_dir = Path(base_dir).resolve() if base_dir else Path(__file__).parent.parent.resolve()
        self.config_generator = config_generator or ConfigGenerator(str(self.base_dir))
        self.evaluator = evaluator or ModelEvaluator(str(self.base_dir))
        self.exporter = exporter or ModelExporter(str(self.base_dir))
        self.notifier = notifier or create_notifier(webhook_url, webhook_type, str(self.base_dir))
        self.report = None
        self.max_backup_runs = max_backup_runs
        logger.info("TrainingPipeline initialized, base_dir=%s, max_backup_runs=%d", self.base_dir, self.max_backup_runs)

    def run(
        self,
        dataset_name: str,
        model: str = "yolov8s.pt",
        imgsz: int = 640,
        batch: int = 16,
        epochs: int = 150,
        class_names: Optional[list] = None,
        skip_validation: bool = False,
        training_overrides: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[str, float], None]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
        enable_tuning: bool = False,
        n_trials: int = 20,
        tuning_metric: str = "metrics/mAP50(B)",
        search_space: Optional[SearchSpace] = None,
        enable_evaluation: bool = True,
        enable_export: bool = False,
        export_formats: Optional[list] = None,
        auto_cleanup: bool = True,
        enable_registry: bool = True,
    ) -> PipelineReport:
        """
        执行完整训练流水线

        Args:
            dataset_name: 数据集子目录名称
            model: 预训练模型
            imgsz: 输入图像尺寸
            batch: 批次大小
            epochs: 训练轮数
            class_names: 类别名称列表
            skip_validation: 是否跳过数据验证
            training_overrides: 训练参数覆盖
            progress_callback: 进度回调函数(stage, progress)
            should_stop: 停止信号检查函数（返回 True 时中断训练）
            enable_tuning: 是否启用超参数搜索
            n_trials: 超参搜索轮数
            tuning_metric: 搜索优化指标
            search_space: 自定义搜索空间
            enable_evaluation: 是否启用评估
            enable_export: 是否启用模型导出
            export_formats: 导出格式列表
            auto_cleanup: 训练完成后是否自动清理旧运行目录

        Returns:
            PipelineReport对象
        """
        dataset_path = self.base_dir / "dataset" / dataset_name
        self.report = PipelineReport(
            dataset_name=dataset_name,
            start_time=datetime.now().isoformat(),
        )

        overall_start = time.time()

        logger.info("=" * 60)
        logger.info("TrainingPipeline started")
        logger.info("  dataset_name: %s", dataset_name)
        logger.info("  dataset_path: %s", dataset_path)
        logger.info("  model: %s", model)
        logger.info("  imgsz: %d", imgsz)
        logger.info("  batch: %d", batch)
        logger.info("  epochs: %d", epochs)
        logger.info("  skip_validation: %s", skip_validation)
        logger.info("  enable_tuning: %s", enable_tuning)
        logger.info("  enable_evaluation: %s", enable_evaluation)
        logger.info("  enable_export: %s", enable_export)
        logger.info("=" * 60)

        # 发送训练开始通知
        self.notifier.notify_training_start(
            dataset_name,
            {"model": model, "imgsz": imgsz, "batch": batch, "epochs": epochs},
        )

        try:
            # Stage 1: 数据验证
            logger.info("[Stage 1/5] Starting data validation...")
            if not skip_validation:
                if progress_callback:
                    progress_callback("validation", 0.0)

                result = self._run_validation(dataset_path)
                self.report.add_stage(result)

                if progress_callback:
                    progress_callback("validation", 1.0)

                if not result.success:
                    logger.error("[Stage 1/5] Data validation FAILED: %s", result.message)
                    logger.error("  Error details: %s", result.error or "N/A")
                    logger.error("  Pipeline aborted due to validation failure")
                    self.notifier.notify_stage_failed(
                        dataset_name=dataset_name,
                        stage="validation",
                        error=result.message,
                        details=result.error,
                    )
                    self._finalize(False)
                    return self.report
                else:
                    logger.info("[Stage 1/5] Data validation PASSED: %s", result.message)
                    stats = result.details.get("stats", {})
                    logger.info("  Dataset stats: %s", json.dumps(stats, ensure_ascii=False))
            else:
                logger.info("[Stage 1/5] Data validation SKIPPED")
                self.report.add_stage(PipelineResult(
                    success=True,
                    stage="validation",
                    message="数据验证已跳过",
                    duration=0.0,
                ))

            # Stage 2: 配置生成
            logger.info("[Stage 2/5] Starting config generation...")
            if progress_callback:
                progress_callback("config_generation", 0.0)

            result = self._run_config_generation(
                dataset_name=dataset_name,
                model=model,
                imgsz=imgsz,
                batch=batch,
                epochs=epochs,
                class_names=class_names,
                overrides=training_overrides,
            )
            self.report.add_stage(result)

            if progress_callback:
                progress_callback("config_generation", 1.0)

            if not result.success:
                logger.error("[Stage 2/5] Config generation FAILED: %s", result.message)
                logger.error("  Error details: %s", result.error or "N/A")
                logger.error("  Pipeline aborted due to config generation failure")
                self.notifier.notify_stage_failed(
                    dataset_name=dataset_name,
                    stage="config_generation",
                    error=result.message,
                    details=result.error,
                )
                self._finalize(False)
                return self.report
            else:
                logger.info("[Stage 2/5] Config generation PASSED")
                config_path = result.details.get("config_path")
                data_yaml = result.details.get("data_yaml")
                logger.info("  Config saved to: %s", config_path)
                logger.info("  data.yaml path: %s", data_yaml)

            data_yaml_path = result.details.get("data_yaml")
            if not data_yaml_path:
                logger.error("[Stage 2/5] Config generation returned no data_yaml path")
                self._finalize(False)
                return self.report

            # 从config_generation阶段的结果中获取project_config
            project_config = result.details.get("project_config")
            if not project_config:
                logger.error("[Stage 2/5] Config generation returned no project_config")
                self._finalize(False)
                return self.report

            # Stage 2.5: 超参数搜索（可选）
            if enable_tuning:
                logger.info("[Stage 2.5/5] Starting hyperparameter tuning (n_trials=%d, metric=%s)...", n_trials, tuning_metric)
                if progress_callback:
                    progress_callback("hyperparameter_tuning", 0.0)

                result = self._run_hyperparameter_tuning(
                    data_yaml_path=data_yaml_path,
                    dataset_name=dataset_name,
                    n_trials=n_trials,
                    metric=tuning_metric,
                    search_space=search_space,
                )
                self.report.add_stage(result)

                if progress_callback:
                    progress_callback("hyperparameter_tuning", 1.0)

                if not result.success:
                    logger.error("[Stage 2.5/5] Hyperparameter tuning FAILED: %s", result.message)
                    logger.error("  Error details: %s", result.error or "N/A")
                    logger.error("  Pipeline aborted due to tuning failure")
                    self._finalize(False)
                    return self.report
                else:
                    logger.info("[Stage 2.5/5] Hyperparameter tuning PASSED")
                    best_params = result.details.get("best_params", {})
                    best_value = result.details.get("best_value", 0.0)
                    logger.info("  Best %s: %.4f", tuning_metric, best_value)
                    logger.info("  Best params: %s", json.dumps(best_params, ensure_ascii=False, indent=2))

                # 使用搜索到的最优参数更新配置
                tuning_result = result.details.get("tuning_result")
                if tuning_result:
                    project_config = self._apply_tuned_params(
                        project_config, tuning_result.best_params, epochs
                    )
                    logger.info("  Tuned params applied to training config")
            else:
                logger.info("[Stage 2.5/5] Hyperparameter tuning SKIPPED")

            # Stage 3: 训练执行
            logger.info("[Stage 3/5] Starting model training...")
            logger.info("  Training config: model=%s, imgsz=%d, batch=%d, epochs=%d",
                        project_config.training_config.model,
                        project_config.training_config.imgsz,
                        project_config.training_config.batch,
                        project_config.training_config.epochs)
            if progress_callback:
                progress_callback("training", 0.0)

            result = self._run_training(project_config, should_stop=should_stop)
            self.report.add_stage(result)

            if progress_callback:
                progress_callback("training", 1.0)

            if not result.success:
                logger.error("[Stage 3/5] Model training FAILED: %s", result.message)
                logger.error("  Error details: %s", result.error or "N/A")
                logger.error("  Pipeline aborted due to training failure")
                self.notifier.notify_stage_failed(
                    dataset_name=dataset_name,
                    stage="training",
                    error=result.message,
                    details=result.error,
                )
                self._finalize(False)
                return self.report
            else:
                logger.info("[Stage 3/5] Model training PASSED")
                best_model_path = result.details.get("best_model")
                metrics = result.details.get("metrics", {})
                logger.info("  Best model saved to: %s", best_model_path)
                logger.info("  Training metrics: %s", json.dumps(metrics, ensure_ascii=False, indent=2))

            best_model_path = result.details.get("best_model")

            # Stage 4: 模型评估（可选）
            if enable_evaluation and best_model_path:
                logger.info("[Stage 4/5] Starting model evaluation...")
                logger.info("  Model: %s", best_model_path)
                if progress_callback:
                    progress_callback("evaluation", 0.0)

                result = self._run_evaluation(
                    model_path=best_model_path,
                    data_yaml=data_yaml_path,
                    dataset_name=dataset_name,
                    imgsz=project_config.training_config.imgsz,
                    batch=project_config.training_config.batch,
                )
                self.report.add_stage(result)

                if progress_callback:
                    progress_callback("evaluation", 1.0)

                if not result.success:
                    logger.warning("[Stage 4/5] Model evaluation FAILED: %s", result.message)
                    logger.warning("  Error details: %s", result.error or "N/A")
                    logger.warning("  Continuing pipeline despite evaluation failure")
                else:
                    logger.info("[Stage 4/5] Model evaluation PASSED")
                    eval_metrics = result.details.get("metrics", {})
                    logger.info("  Evaluation metrics: %s", json.dumps(eval_metrics, ensure_ascii=False, indent=2))
            else:
                logger.info("[Stage 4/5] Model evaluation SKIPPED")

            # Stage 5: 模型导出（可选）
            if enable_export and best_model_path:
                logger.info("[Stage 5/5] Starting model export...")
                logger.info("  Model: %s", best_model_path)
                logger.info("  Formats: %s", export_formats or ["onnx", "engine"])
                if progress_callback:
                    progress_callback("export", 0.0)

                result = self._run_export(
                    model_path=best_model_path,
                    formats=export_formats,
                    imgsz=project_config.training_config.imgsz,
                )
                self.report.add_stage(result)

                if progress_callback:
                    progress_callback("export", 1.0)

                if not result.success:
                    logger.warning("[Stage 5/5] Model export FAILED: %s", result.message)
                    logger.warning("  Error details: %s", result.error or "N/A")
                    logger.warning("  Continuing pipeline despite export failure")
                else:
                    logger.info("[Stage 5/5] Model export PASSED")
                    export_details = result.details.get("export_report", {})
                    logger.info("  Export results: %s", json.dumps(export_details, ensure_ascii=False, indent=2))
            else:
                logger.info("[Stage 5/5] Model export SKIPPED")

            # 自动清理旧训练目录
            if auto_cleanup:
                self._cleanup_old_runs(dataset_name)

            # 注册到 ModelRegistry（默认启用）
            if enable_registry and best_model_path:
                try:
                    from src.model_registry import ModelRegistry
                    from dataclasses import asdict
                    registry = ModelRegistry(str(self.base_dir))
                    train_cfg = project_config.training_config
                    # 优先用评估指标（Stage 4），否则用训练指标（Stage 3）
                    reported_metrics = locals().get("eval_metrics") or metrics or {}
                    version = registry.register(
                        model_path=str(best_model_path),
                        dataset_name=dataset_name,
                        metrics={k: float(v) for k, v in reported_metrics.items() if isinstance(v, (int, float))},
                        params={
                            "model": train_cfg.model,
                            "epochs": train_cfg.epochs,
                            "imgsz": train_cfg.imgsz,
                            "batch": train_cfg.batch,
                            "lr0": train_cfg.lr0,
                            "optimizer": train_cfg.optimizer,
                        },
                        tags=[
                            f"epochs={train_cfg.epochs}",
                            f"imgsz={train_cfg.imgsz}",
                            f"batch={train_cfg.batch}",
                        ],
                        description=project_config.description or f"Auto-trained on {dataset_name}",
                        copy_model=False,  # 不复制，保留 runs/detect/ 原位
                    )
                    logger.info("Model registered: %s", version.version_id)
                except Exception as e:
                    logger.warning("Model registry step skipped: %s", e)

            # 全部成功
            logger.info("=" * 60)
            logger.info("TrainingPipeline completed SUCCESSFULLY")
            logger.info("  Total stages: %d", len(self.report.stages))
            logger.info("  Total duration: %.2f seconds", time.time() - overall_start)
            logger.info("=" * 60)
            self._finalize(True)

            # 发送训练完成通知
            final_metrics = {}
            for stage in self.report.stages:
                if stage["stage"] == "training" and stage["success"]:
                    final_metrics = stage["details"].get("metrics", {})
                    break

            self.notifier.notify_training_complete(
                dataset_name,
                final_metrics,
                self.report.total_duration,
            )

            return self.report

        except Exception as e:
            error_msg = str(e)
            logger.critical("TrainingPipeline encountered CRITICAL ERROR: %s", error_msg)
            logger.critical("Traceback: %s", traceback.format_exc())
            self.report.add_stage(PipelineResult(
                success=False,
                stage="pipeline",
                message=f"流水线执行异常: {error_msg}",
                duration=time.time() - overall_start,
                error=traceback.format_exc(),
            ))
            self._finalize(False)

            # 发送错误通知
            self.notifier.notify_training_error(dataset_name, error_msg)

            return self.report

    def _run_validation(self, dataset_path: Path) -> PipelineResult:
        """执行数据验证阶段"""
        start = time.time()
        logger.info("  -> Validating dataset at: %s", dataset_path)

        try:
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
            msg = f"数据验证通过"
            if warnings:
                msg += f"，发现 {len(warnings)} 个警告"
                logger.warning("  -> Validation found %d warnings", len(warnings))
                for warn in warnings[:5]:
                    logger.warning("     - [%s] %s", warn.category, warn.message)

            logger.info("  -> Validation passed in %.2f seconds", duration)
            return PipelineResult(
                success=True,
                stage="validation",
                message=msg,
                duration=duration,
                details={
                    "report": report.to_dict(),
                    "stats": report.stats,
                },
            )

        except Exception as e:
            logger.error("  -> Validation exception: %s", str(e))
            return PipelineResult(
                success=False,
                stage="validation",
                message=f"数据验证异常: {str(e)}",
                duration=time.time() - start,
                error=traceback.format_exc(),
            )

    def _run_config_generation(
        self,
        dataset_name: str,
        model: str,
        imgsz: int,
        batch: int,
        epochs: int,
        class_names: Optional[list],
        overrides: Optional[Dict[str, Any]],
    ) -> PipelineResult:
        """执行配置生成阶段"""
        start = time.time()
        logger.info("  -> Generating config for dataset: %s", dataset_name)
        logger.info("     Model: %s, imgsz: %d, batch: %d, epochs: %d", model, imgsz, batch, epochs)
        if overrides:
            logger.info("     Overrides: %s", json.dumps(overrides, ensure_ascii=False))

        try:
            config = self.config_generator.generate_project_config(
                dataset_name=dataset_name,
                model=model,
                imgsz=imgsz,
                batch=batch,
                epochs=epochs,
                class_names=class_names,
                description=f"Auto-generated training for {dataset_name}",
                overrides=overrides,
            )

            # 保存配置
            config_path = self.config_generator.save_project_config(config)

            duration = time.time() - start
            logger.info("  -> Config generated in %.2f seconds", duration)
            logger.info("     Config saved to: %s", config_path)
            logger.info("     data.yaml path: %s", config.data_yaml_path)

            return PipelineResult(
                success=True,
                stage="config_generation",
                message="配置生成成功",
                duration=duration,
                details={
                    "config_path": config_path,
                    "data_yaml": config.data_yaml_path,
                    "project_config": config,
                },
            )

        except Exception as e:
            logger.error("  -> Config generation exception: %s", str(e))
            return PipelineResult(
                success=False,
                stage="config_generation",
                message=f"配置生成失败: {str(e)}",
                duration=time.time() - start,
                error=traceback.format_exc(),
            )

    def _run_hyperparameter_tuning(
        self,
        data_yaml_path: str,
        dataset_name: str,
        n_trials: int,
        metric: str,
        search_space: Optional[SearchSpace],
    ) -> PipelineResult:
        """执行超参数搜索阶段"""
        start = time.time()
        logger.info("  -> Starting hyperparameter tuning")
        logger.info("     data_yaml: %s", data_yaml_path)
        logger.info("     n_trials: %d, metric: %s", n_trials, metric)

        try:
            tuner = YOLOHyperparameterTuner(
                data_yaml_path=data_yaml_path,
                base_dir=str(self.base_dir),
                study_name=f"{dataset_name}_tuning",
            )

            result = tuner.tune(
                n_trials=n_trials,
                search_space=search_space,
                metric=metric,
            )

            duration = time.time() - start
            logger.info("  -> Hyperparameter tuning completed in %.2f seconds", duration)
            logger.info("     Best %s: %.4f", metric, result.best_value)
            logger.info("     Best params: %s", json.dumps(result.best_params, ensure_ascii=False, indent=2))
            logger.info("     Total trials: %d", result.n_trials)

            return PipelineResult(
                success=True,
                stage="hyperparameter_tuning",
                message=f"超参搜索完成，最优{metric}={result.best_value:.4f}",
                duration=duration,
                details={
                    "tuning_result": result,
                    "best_params": result.best_params,
                    "best_value": result.best_value,
                    "n_trials": result.n_trials,
                },
            )

        except ImportError:
            logger.error("  -> Hyperparameter tuning failed: optuna not installed")
            return PipelineResult(
                success=False,
                stage="hyperparameter_tuning",
                message="未安装optuna，无法执行超参搜索",
                duration=time.time() - start,
                error="ImportError: optuna not found",
            )

        except Exception as e:
            logger.error("  -> Hyperparameter tuning exception: %s", str(e))
            return PipelineResult(
                success=False,
                stage="hyperparameter_tuning",
                message=f"超参搜索失败: {str(e)}",
                duration=time.time() - start,
                error=traceback.format_exc(),
            )

    def _apply_tuned_params(
        self,
        project_config: ProjectConfig,
        best_params: Dict[str, Any],
        full_epochs: int,
    ) -> ProjectConfig:
        """将搜索到的最优参数应用到配置中"""
        cfg = project_config.training_config
        logger.info("  -> Applying tuned params to training config")
        logger.info("     Original epochs: %d -> New epochs: %d", cfg.epochs, full_epochs)

        # 更新搜索到的参数
        for key, value in best_params.items():
            if hasattr(cfg, key):
                old_value = getattr(cfg, key)
                setattr(cfg, key, value)
                logger.info("     %s: %s -> %s", key, old_value, value)

        # 使用完整轮数进行最终训练
        cfg.epochs = full_epochs

        # 恢复完整训练设置：仅在未被搜索或用户覆盖时设置默认值
        if not hasattr(cfg, "patience") or cfg.patience is None:
            cfg.patience = 30
        if not hasattr(cfg, "save") or cfg.save is None:
            cfg.save = True
        if not hasattr(cfg, "plots") or cfg.plots is None:
            cfg.plots = True
        if not hasattr(cfg, "verbose") or cfg.verbose is None:
            cfg.verbose = True

        logger.info("  -> Tuned params applied successfully")
        return project_config

    @staticmethod
    def _release_cuda():
        """释放 GPU 显存并回收垃圾对象，避免连续训练时 OOM"""
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
        except Exception:
            pass
        gc.collect()

    def _run_training(
        self,
        project_config: ProjectConfig,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> PipelineResult:
        """执行训练阶段（封装Ultralytics API）"""
        start = time.time()
        cfg = project_config.training_config
        logger.info("  -> Starting model training")
        logger.info("     Model: %s", cfg.model)
        logger.info("     Epochs: %d, imgsz: %d, batch: %d", cfg.epochs, cfg.imgsz, cfg.batch)
        logger.info("     Optimizer: %s, lr0: %.6f", cfg.optimizer, cfg.lr0)

        try:
            from ultralytics import YOLO

            # 提前加载模型，让加载过程在日志中可见
            model_path = self.config_generator.resolve_model_path(cfg.model)
            logger.info("     Resolved model path: %s", model_path)
            logger.info("     Loading YOLO model from: %s", model_path)
            logger.info("     This may take a moment to initialize...")

            try:
                import torch
                if torch.cuda.is_available():
                    gpu_name = torch.cuda.get_device_name(0)
                    gpu_mem = torch.cuda.get_device_properties(0).total_mem / (1024**3)
                    logger.info("     GPU: %s (%.1f GB VRAM)", gpu_name, gpu_mem)
                else:
                    logger.info("     GPU: Not available, using CPU")
            except Exception as e:
                logger.debug("     GPU info collection failed: %s", e)

            model = YOLO(model_path)
            logger.info("     Model loaded successfully")

            # 注册停止回调：每个 epoch 结束后检查是否应该停止
            if should_stop:
                def _on_epoch_end(trainer):
                    if should_stop():
                        logger.info("[TRAINING] 收到停止信号，正在优雅停止训练...")
                        trainer.stop_training = True

                model.add_callback("on_epoch_end", _on_epoch_end)

            # 构建训练参数
            train_kwargs = cfg.to_dict()
            train_kwargs.pop("model", None)

            # 使用 project_config 中已定义的项目名和运行名，确保一致性
            # 必须使用绝对路径，否则 Ultralytics 连续训练时可能因 cwd 变化而生成嵌套目录
            output_dir = Path(project_config.output_dir).resolve()
            train_kwargs["project"] = str(output_dir.parent)
            train_kwargs["name"] = output_dir.name

            logger.info("     Project: %s", train_kwargs["project"])
            logger.info("     Run name: %s", train_kwargs["name"])

            # 执行训练
            results = model.train(
                data=str(Path(project_config.data_yaml_path).resolve()),
                **train_kwargs,
            )

            duration = time.time() - start
            logger.info("  -> Model training completed in %.2f seconds", duration)

            # 提取关键指标
            metrics = {}
            if hasattr(results, "results_dict"):
                metrics = results.results_dict
                logger.info("     Final metrics: %s", json.dumps(metrics, ensure_ascii=False, indent=2))

            # Ultralytics 在目标目录已存在时会自动加 -2/-3 等后缀，
            # 且训练过程中可能切换工作目录，因此直接从 project 目录下按运行名前缀找最新目录，并返回绝对路径。
            project_dir = Path(train_kwargs["project"]).resolve()
            intended_name = train_kwargs["name"]
            run_dirs = [
                d for d in project_dir.iterdir()
                if d.is_dir() and d.name.startswith(intended_name)
            ]
            if run_dirs:
                actual_run_dir = max(run_dirs, key=lambda p: p.stat().st_mtime).resolve()
            else:
                actual_run_dir = Path(project_config.output_dir).resolve()
            best_model_path = str(actual_run_dir / "weights" / "best.pt")
            logger.info("     Best model saved to: %s", best_model_path)

            self._release_cuda()
            return PipelineResult(
                success=True,
                stage="training",
                message="训练完成",
                duration=duration,
                details={
                    "metrics": metrics,
                    "best_model": best_model_path,
                },
            )

        except ImportError:
            logger.error("  -> Model training failed: ultralytics not installed")
            self._release_cuda()
            return PipelineResult(
                success=False,
                stage="training",
                message="未安装ultralytics，无法执行训练",
                duration=time.time() - start,
                error="ImportError: ultralytics not found",
            )

        except Exception as e:
            logger.error("  -> Model training exception: %s", str(e))
            self._release_cuda()
            return PipelineResult(
                success=False,
                stage="training",
                message=f"训练失败: {str(e)}",
                duration=time.time() - start,
                error=traceback.format_exc(),
            )

    def _run_evaluation(
        self,
        model_path: str,
        data_yaml: str,
        dataset_name: str,
        imgsz: int,
        batch: int,
    ) -> PipelineResult:
        """执行评估阶段"""
        start = time.time()
        logger.info("  -> Starting model evaluation")
        logger.info("     Model: %s", model_path)
        logger.info("     data_yaml: %s", data_yaml)

        try:
            report = self.evaluator.evaluate(
                model_path=model_path,
                data_yaml=data_yaml,
                dataset_name=dataset_name,
                imgsz=imgsz,
                batch=batch,
            )

            duration = time.time() - start
            logger.info("  -> Model evaluation completed in %.2f seconds", duration)
            logger.info("     mAP@50: %.4f", report.metrics.mAP50)
            logger.info("     mAP@50-95: %.4f", report.metrics.mAP50_95)
            logger.info("     Precision: %.4f, Recall: %.4f", report.metrics.precision, report.metrics.recall)

            # 发送评估完成通知
            self.notifier.notify_evaluation_complete(
                dataset_name,
                model_path,
                report.metrics.to_dict(),
            )

            return PipelineResult(
                success=True,
                stage="evaluation",
                message=f"评估完成，mAP@50={report.metrics.mAP50:.4f}",
                duration=duration,
                details={
                    "metrics": report.metrics.to_dict(),
                    "report_path": str(self.evaluator.reports_dir),
                },
            )

        except Exception as e:
            logger.error("  -> Model evaluation exception: %s", str(e))
            return PipelineResult(
                success=False,
                stage="evaluation",
                message=f"评估失败: {str(e)}",
                duration=time.time() - start,
                error=traceback.format_exc(),
            )

    def _run_export(
        self,
        model_path: str,
        formats: Optional[list],
        imgsz: int,
    ) -> PipelineResult:
        """执行模型导出阶段"""
        start = time.time()
        logger.info("  -> Starting model export")
        logger.info("     Model: %s", model_path)
        logger.info("     Formats: %s", formats or ["onnx", "engine"])
        logger.info("     imgsz: %d", imgsz)

        try:
            report = self.exporter.export(
                model_path=model_path,
                formats=formats,
                imgsz=imgsz,
            )

            duration = time.time() - start
            success_count = report.success_count
            total_count = report.total_count

            logger.info("  -> Model export completed in %.2f seconds", duration)
            logger.info("     Success: %d/%d formats exported", success_count, total_count)
            for result in report.results:
                if result.success:
                    logger.info("     [OK] %s -> %s (%.2f MB)", result.format, result.output_path, result.file_size_mb)
                else:
                    logger.warning("     [FAIL] %s: %s", result.format, result.message)

            return PipelineResult(
                success=success_count > 0,
                stage="export",
                message=f"模型导出完成 ({success_count}/{total_count} 成功)",
                duration=duration,
                details={
                    "export_report": report.to_dict(),
                },
            )

        except Exception as e:
            logger.error("  -> Model export exception: %s", str(e))
            return PipelineResult(
                success=False,
                stage="export",
                message=f"模型导出失败: {str(e)}",
                duration=time.time() - start,
                error=traceback.format_exc(),
            )

    def _cleanup_old_runs(self, dataset_name: str):
        """清理旧的训练运行目录，仅保留最新的 max_backup_runs 轮"""
        import shutil
        import re

        runs_dir = self.base_dir / "runs" / "detect"
        if not runs_dir.exists():
            return

        # 匹配当前数据集的训练目录: {dataset_name}_auto, {dataset_name}_auto-2, {dataset_name}_auto-3, ...
        pattern = re.compile(rf"^{re.escape(dataset_name)}_auto(-\d+)?$")

        run_dirs = []
        for item in runs_dir.iterdir():
            if item.is_dir() and pattern.match(item.name):
                # 获取目录修改时间
                try:
                    mtime = item.stat().st_mtime
                    run_dirs.append((item, mtime))
                except OSError:
                    continue

        # 按修改时间排序（最新的在前）
        run_dirs.sort(key=lambda x: x[1], reverse=True)

        # 保留最新的 max_backup_runs 个，删除其余的
        keep_count = self.max_backup_runs
        total_runs = len(run_dirs)

        if total_runs <= keep_count:
            logger.info("[Cleanup] Found %d run(s), keeping all (max_backup=%d)", total_runs, keep_count)
            return

        logger.info("[Cleanup] Found %d run(s), keeping latest %d, removing %d old run(s)",
                    total_runs, keep_count, total_runs - keep_count)

        for run_dir, _ in run_dirs[keep_count:]:
            try:
                shutil.rmtree(run_dir)
                logger.info("[Cleanup] Removed old run directory: %s", run_dir.name)
            except Exception as e:
                logger.warning("[Cleanup] Failed to remove %s: %s", run_dir.name, e)

        # 同时清理评估目录（保留最新的一个）
        eval_pattern = re.compile(rf"^{re.escape(dataset_name)}_eval(-\d+)?$")
        eval_dirs = []
        for item in runs_dir.iterdir():
            if item.is_dir() and eval_pattern.match(item.name):
                try:
                    mtime = item.stat().st_mtime
                    eval_dirs.append((item, mtime))
                except OSError:
                    continue

        eval_dirs.sort(key=lambda x: x[1], reverse=True)
        if len(eval_dirs) > 1:
            for eval_dir, _ in eval_dirs[1:]:
                try:
                    shutil.rmtree(eval_dir)
                    logger.info("[Cleanup] Removed old eval directory: %s", eval_dir.name)
                except Exception as e:
                    logger.warning("[Cleanup] Failed to remove eval %s: %s", eval_dir.name, e)

    def _finalize(self, success: bool):
        """完成流水线，生成最终报告"""
        self.report.end_time = datetime.now().isoformat()
        self.report.success = success

        # 计算总耗时
        if self.report.stages:
            self.report.total_duration = sum(s["duration"] for s in self.report.stages)

        # 保存报告
        reports_dir = self.base_dir / "reports"
        reports_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = reports_dir / f"pipeline_{self.report.dataset_name}_{timestamp}.json"

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(self.report.to_dict(), f, indent=2, ensure_ascii=False)

        logger.info("Pipeline report saved to: %s", report_path)
        logger.info("Pipeline final status: %s", "SUCCESS" if success else "FAILED")
        logger.info("Total stages executed: %d", len(self.report.stages))
        for stage in self.report.stages:
            status_str = "PASS" if stage["success"] else "FAIL"
            logger.info("  [%s] %s: %s (%.2f s)", status_str, stage["stage"], stage["message"], stage["duration"])


def run_training(
    dataset_name: str,
    model: str = "yolov8s.pt",
    imgsz: int = 640,
    batch: int = 16,
    epochs: int = 150,
    skip_validation: bool = False,
    base_dir: Optional[str] = None,
    enable_tuning: bool = False,
    n_trials: int = 20,
    tuning_metric: str = "metrics/mAP50(B)",
    enable_evaluation: bool = True,
    enable_export: bool = False,
    export_formats: Optional[list] = None,
    auto_cleanup: bool = True,
    max_backup_runs: int = 2,
    training_overrides: Optional[Dict[str, Any]] = None,
) -> PipelineReport:
    """
    便捷函数：一键执行训练流水线

    Args:
        dataset_name: 数据集子目录名称（如 'cabel-damage-mini'）
        model: 预训练模型
        imgsz: 输入图像尺寸
        batch: 批次大小
        epochs: 训练轮数
        skip_validation: 是否跳过数据验证
        base_dir: 项目根目录
        enable_tuning: 是否启用超参数搜索
        n_trials: 超参搜索轮数
        tuning_metric: 搜索优化指标
        enable_evaluation: 是否启用评估
        enable_export: 是否启用模型导出
        export_formats: 导出格式列表
        auto_cleanup: 训练完成后是否自动清理旧运行目录
        max_backup_runs: 保留的最大历史运行目录数量
        training_overrides: 训练参数覆盖字典

    Returns:
        PipelineReport对象
    """
    pipeline = TrainingPipeline(base_dir, max_backup_runs=max_backup_runs)
    return pipeline.run(
        dataset_name=dataset_name,
        model=model,
        imgsz=imgsz,
        batch=batch,
        epochs=epochs,
        skip_validation=skip_validation,
        enable_tuning=enable_tuning,
        n_trials=n_trials,
        tuning_metric=tuning_metric,
        enable_evaluation=enable_evaluation,
        enable_export=enable_export,
        export_formats=export_formats,
        auto_cleanup=auto_cleanup,
        training_overrides=training_overrides,
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python training_pipeline.py <dataset_name> [model] [imgsz] [batch] [epochs]")
        print("示例: python training_pipeline.py cabel-damage-mini yolov8s.pt 640 16 150")
        sys.exit(1)

    dataset_name = sys.argv[1]
    model = sys.argv[2] if len(sys.argv) > 2 else "yolov8s.pt"
    imgsz = int(sys.argv[3]) if len(sys.argv) > 3 else 640
    batch = int(sys.argv[4]) if len(sys.argv) > 4 else 16
    epochs = int(sys.argv[5]) if len(sys.argv) > 5 else 150

    print(f"启动训练流水线...")
    print(f"  数据集: {dataset_name}")
    print(f"  模型: {model}")
    print(f"  图像尺寸: {imgsz}")
    print(f"  批次: {batch}")
    print(f"  轮数: {epochs}")
    print("-" * 50)

    report = run_training(dataset_name, model, imgsz, batch, epochs)

    print("-" * 50)
    print(f"流水线执行结果: {'成功' if report.success else '失败'}")
    print(f"总耗时: {report.total_duration:.2f}秒")
    print(f"阶段详情:")
    for stage in report.stages:
        status = "OK" if stage["success"] else "FAIL"
        print(f"  [{status}] {stage['stage']}: {stage['message']} ({stage['duration']:.2f}s)")

    # 保存报告路径
    print(f"\n详细报告已保存")
