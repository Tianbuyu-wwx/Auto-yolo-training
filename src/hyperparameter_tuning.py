"""
Optuna超参数自动搜索模块
基于验证集mAP自动寻找最优训练超参数
"""

import os
import sys
import json
import time
import shutil
import traceback
import tempfile
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable, Tuple

import optuna
from optuna.samplers import TPESampler
from optuna.pruners import MedianPruner

from src.utils import resolve_model_path


# ----------------------------------------------------------------------
# 嵌套 dataclass：阶段 A11 引入，兼容旧 _min/_max 字段
# ----------------------------------------------------------------------
@dataclass
class IntRange:
    """整数范围（含 step）。"""
    min: int
    max: int
    step: int = 1


@dataclass
class FloatRange:
    """浮点范围。``log=True`` 用于学习率/权重衰减等几何分布场景。"""
    min: float
    max: float
    log: bool = False


@dataclass
class CategoryRange:
    """分类选项列表。"""
    choices: List[Any]


def _int(default_min: int, default_max: int, default_step: int = 1) -> IntRange:
    return IntRange(min=default_min, max=default_max, step=default_step)


def _float(default_min: float, default_max: float, log: bool = False) -> FloatRange:
    return FloatRange(min=default_min, max=default_max, log=log)


@dataclass
class SearchSpace:
    """超参数搜索空间定义。

    设计变更（2026-09-02）：为统一表达嵌套范围，新增 IntRange / FloatRange /
    CategoryRange 类型（嵌套 dataclass，**新增** ``ranges`` 字段）。同时保留
    所有旧 ``_min`` / ``_max`` / ``_step`` 字段，通过 property 转发到 ``ranges``，
    保证 ``tune.py`` 和 ``_sample_params`` 的现有调用点不破。阶段 B 再彻底删除
    旧字段。
    """
    # 模型选择
    model_candidates: List[str] = field(default_factory=lambda: ["yolov8s.pt", "yolov8m.pt"])

    # 图像尺寸
    imgsz_min: int = 640
    imgsz_max: int = 1280
    imgsz_step: int = 640

    # 批次大小
    batch_min: int = 4
    batch_max: int = 16
    batch_step: int = 4

    # 学习率
    lr0_min: float = 1e-4
    lr0_max: float = 1e-2
    lr0_log: bool = True

    # 优化器
    optimizer_candidates: List[str] = field(default_factory=lambda: ["AdamW", "SGD", "NAdam", "RAdam"])

    # 学习率调度
    cos_lr_candidates: List[bool] = field(default_factory=lambda: [True, False])

    # 数据增强
    mosaic_min: float = 0.5
    mosaic_max: float = 1.0

    mixup_min: float = 0.0
    mixup_max: float = 0.3

    degrees_min: float = 0.0
    degrees_max: float = 15.0

    scale_min: float = 0.3
    scale_max: float = 0.7

    translate_min: float = 0.0
    translate_max: float = 0.2

    shear_min: float = 0.0
    shear_max: float = 5.0

    perspective_min: float = 0.0
    perspective_max: float = 0.0005

    flipud_min: float = 0.0
    flipud_max: float = 0.5

    hsv_h_min: float = 0.0
    hsv_h_max: float = 0.03

    hsv_s_min: float = 0.4
    hsv_s_max: float = 1.0

    hsv_v_min: float = 0.2
    hsv_v_max: float = 0.6

    copy_paste_min: float = 0.0
    copy_paste_max: float = 0.1

    close_mosaic_min: int = 5
    close_mosaic_max: int = 15

    # 正则化
    dropout_min: float = 0.0
    dropout_max: float = 0.2

    label_smoothing_min: float = 0.0
    label_smoothing_max: float = 0.1

    weight_decay_min: float = 1e-4
    weight_decay_max: float = 1e-3
    weight_decay_log: bool = True

    freeze_min: int = 0
    freeze_max: int = 10

    # 损失权重
    box_min: float = 5.0
    box_max: float = 10.0

    cls_min: float = 0.3
    cls_max: float = 1.0

    dfl_min: float = 1.0
    dfl_max: float = 2.0

    # 固定参数（不参与搜索）
    fixed_params: Dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # 嵌套 dataclass 字段（阶段 A11 新增；阶段 B 取代上述扁平字段）
    # ------------------------------------------------------------------
    ranges: Dict[str, Any] = field(default_factory=lambda: {
        "imgsz": _int(640, 1280, 640),
        "batch": _int(4, 16, 4),
        "lr0": _float(1e-4, 1e-2, log=True),
        "mosaic": _float(0.5, 1.0),
        "mixup": _float(0.0, 0.3),
        "degrees": _float(0.0, 15.0),
        "scale": _float(0.3, 0.7),
        "translate": _float(0.0, 0.2),
        "shear": _float(0.0, 5.0),
        "perspective": _float(0.0, 0.0005),
        "flipud": _float(0.0, 0.5),
        "hsv_h": _float(0.0, 0.03),
        "hsv_s": _float(0.4, 1.0),
        "hsv_v": _float(0.2, 0.6),
        "copy_paste": _float(0.0, 0.1),
        "close_mosaic": _int(5, 15),
        "dropout": _float(0.0, 0.2),
        "label_smoothing": _float(0.0, 0.1),
        "weight_decay": _float(1e-4, 1e-3, log=True),
        "freeze": _int(0, 10),
        "box": _float(5.0, 10.0),
        "cls": _float(0.3, 1.0),
        "dfl": _float(1.0, 2.0),
    })

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_candidates": self.model_candidates,
            "imgsz_range": [self.imgsz_min, self.imgsz_max, self.imgsz_step],
            "batch_range": [self.batch_min, self.batch_max, self.batch_step],
            "lr0_range": [self.lr0_min, self.lr0_max],
            "optimizer_candidates": self.optimizer_candidates,
            "cos_lr_candidates": self.cos_lr_candidates,
            "mosaic_range": [self.mosaic_min, self.mosaic_max],
            "mixup_range": [self.mixup_min, self.mixup_max],
            "degrees_range": [self.degrees_min, self.degrees_max],
            "scale_range": [self.scale_min, self.scale_max],
            "translate_range": [self.translate_min, self.translate_max],
            "shear_range": [self.shear_min, self.shear_max],
            "perspective_range": [self.perspective_min, self.perspective_max],
            "flipud_range": [self.flipud_min, self.flipud_max],
            "hsv_h_range": [self.hsv_h_min, self.hsv_h_max],
            "hsv_s_range": [self.hsv_s_min, self.hsv_s_max],
            "hsv_v_range": [self.hsv_v_min, self.hsv_v_max],
            "copy_paste_range": [self.copy_paste_min, self.copy_paste_max],
            "close_mosaic_range": [self.close_mosaic_min, self.close_mosaic_max],
            "dropout_range": [self.dropout_min, self.dropout_max],
            "label_smoothing_range": [self.label_smoothing_min, self.label_smoothing_max],
            "weight_decay_range": [self.weight_decay_min, self.weight_decay_max],
            "freeze_range": [self.freeze_min, self.freeze_max],
            "box_range": [self.box_min, self.box_max],
            "cls_range": [self.cls_min, self.cls_max],
            "dfl_range": [self.dfl_min, self.dfl_max],
            "fixed_params": self.fixed_params,
        }


@dataclass
class TuningResult:
    """超参搜索结果"""
    best_params: Dict[str, Any]
    best_value: float
    n_trials: int
    study_name: str
    duration: float
    all_trials: List[Dict[str, Any]] = field(default_factory=list)
    optimization_direction: str = "maximize"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "best_params": self.best_params,
            "best_value": self.best_value,
            "n_trials": self.n_trials,
            "study_name": self.study_name,
            "duration": self.duration,
            "optimization_direction": self.optimization_direction,
            "all_trials": self.all_trials,
        }


class YOLOHyperparameterTuner:
    """YOLO超参数调优器"""

    def __init__(
        self,
        data_yaml_path: str,
        base_dir: Optional[str] = None,
        study_name: Optional[str] = None,
        storage: Optional[str] = None,
    ):
        self.data_yaml_path = Path(data_yaml_path)
        self.base_dir = Path(base_dir) if base_dir else Path(__file__).parent.parent
        self.study_name = study_name or f"yolo_tuning_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.storage = storage

        # 创建调优结果目录
        self.tuning_dir = self.base_dir / "tuning"
        self.tuning_dir.mkdir(exist_ok=True)

        # 底模目录
        self.basemodels_dir = self.base_dir / "basemodels"

        # 临时目录用于存放trial训练结果
        self._temp_dir_created = False
        self.temp_dir = self._create_temp_dir()

    def _create_temp_dir(self) -> Path:
        """创建临时目录，并标记为已创建"""
        temp = Path(tempfile.mkdtemp(prefix="yolo_tuning_"))
        self._temp_dir_created = True
        return temp

    def resolve_model_path(self, model: str) -> str:
        """解析模型路径（委托给公共工具函数）"""
        return resolve_model_path(model, self.basemodels_dir)

    def tune(
        self,
        n_trials: int = 20,
        search_space: Optional[SearchSpace] = None,
        metric: str = "metrics/mAP50(B)",
        direction: str = "maximize",
        timeout: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int, float], None]] = None,
    ) -> TuningResult:
        """
        执行超参数搜索

        Args:
            n_trials: 搜索轮数
            search_space: 搜索空间定义
            metric: 优化指标
            direction: 优化方向 (maximize/minimize)
            timeout: 超时时间（秒）
            progress_callback: 进度回调(trial_no, total_trials, best_value)

        Returns:
            TuningResult对象
        """
        if search_space is None:
            search_space = SearchSpace()

        self.search_space = search_space
        self.metric = metric
        self.progress_callback = progress_callback

        start_time = time.time()

        # 创建Optuna study
        sampler = TPESampler(seed=42)
        pruner = MedianPruner(
            n_startup_trials=3,
            n_warmup_steps=10,
            interval_steps=1,
        )

        study = optuna.create_study(
            study_name=self.study_name,
            direction=direction,
            sampler=sampler,
            pruner=pruner,
            storage=self.storage,
        )

        # 执行搜索
        study.optimize(
            func=self._objective,
            n_trials=n_trials,
            timeout=timeout,
            show_progress_bar=True,
        )

        duration = time.time() - start_time

        # 收集所有trial结果
        all_trials = []
        for trial in study.trials:
            if trial.state == optuna.trial.TrialState.COMPLETE:
                all_trials.append({
                    "number": trial.number,
                    "params": trial.params,
                    "value": trial.value,
                    "duration": trial.duration.total_seconds() if trial.duration else None,
                })

        result = TuningResult(
            best_params=study.best_params,
            best_value=study.best_value,
            n_trials=len(study.trials),
            study_name=self.study_name,
            duration=duration,
            all_trials=all_trials,
            optimization_direction=direction,
        )

        # 保存结果
        self._save_result(result)

        return result

    def _objective(self, trial: optuna.Trial) -> float:
        """Optuna目标函数"""
        trial_output = None
        try:
            from ultralytics import YOLO

            # 从搜索空间采样参数
            params = self._sample_params(trial)

            # 构建trial专属输出目录
            trial_name = f"trial_{trial.number:03d}"
            trial_output = self.temp_dir / trial_name
            trial_output.mkdir(exist_ok=True)

            # 加载模型（解析底模路径）
            model_path = self.resolve_model_path(params["model"])
            model = YOLO(model_path)

            # 构建训练参数
            train_kwargs = {
                "data": str(self.data_yaml_path),
                "epochs": params.get("epochs", 30),  # 搜索时使用较少轮数
                "imgsz": params["imgsz"],
                "batch": params["batch"],
                "optimizer": params["optimizer"],
                "cos_lr": params.get("cos_lr", True),
                "lr0": params["lr0"],
                "mosaic": params["mosaic"],
                "mixup": params["mixup"],
                "degrees": params["degrees"],
                "scale": params["scale"],
                "translate": params["translate"],
                "shear": params["shear"],
                "perspective": params["perspective"],
                "flipud": params["flipud"],
                "hsv_h": params["hsv_h"],
                "hsv_s": params["hsv_s"],
                "hsv_v": params["hsv_v"],
                "copy_paste": params["copy_paste"],
                "close_mosaic": params["close_mosaic"],
                "dropout": params["dropout"],
                "label_smoothing": params["label_smoothing"],
                "weight_decay": params["weight_decay"],
                "freeze": params["freeze"],
                "box": params["box"],
                "cls": params["cls"],
                "dfl": params["dfl"],
                "project": str(trial_output),
                "name": "train",
                "exist_ok": True,
                "verbose": False,
                "patience": 10,  # 搜索时早停更激进
                "save": False,   # 不保存中间模型
                "plots": False,  # 不生成图表
            }

            # 应用固定参数
            train_kwargs.update(self.search_space.fixed_params)

            # 执行训练
            results = model.train(**train_kwargs)

            # 提取指标
            metric_value = self._extract_metric(results, self.metric)

            # 报告中间结果（用于pruner）- 从csv日志读取epoch级别指标
            try:
                csv_path = Path(train_kwargs.get("project", ".")) / train_kwargs.get("name", "") / "results.csv"
                if csv_path.exists():
                    import csv as csv_mod
                    with open(csv_path, "r", encoding="utf-8") as f:
                        reader = csv_mod.DictReader(f)
                        for step, row in enumerate(reader):
                            # 尝试匹配指标列
                            for col_name, col_val in row.items():
                                if self.metric in col_name and col_name.strip() != self.metric:
                                    try:
                                        intermediate = float(col_val)
                                        trial.report(intermediate, step=step)
                                        if trial.should_prune():
                                            raise optuna.TrialPruned()
                                    except (ValueError, TypeError):
                                        pass
                                    break
            except optuna.TrialPruned:
                raise
            except Exception:
                pass  # 中间结果报告失败不影响训练

            # 进度回调
            if self.progress_callback:
                study = trial.study
                self.progress_callback(
                    trial.number + 1,
                    len(study.trials),
                    study.best_value,
                )

            return metric_value if metric_value is not None else 0.0

        except optuna.TrialPruned:
            raise
        except Exception as e:
            # 记录详细错误信息，便于调试
            error_msg = f"Trial {trial.number} failed: {str(e)}"
            print(f"[ERROR] {error_msg}")
            print(f"[ERROR] Traceback: {traceback.format_exc()}")
            # 将错误信息记录到trial用户属性中
            trial.set_user_attr("error", error_msg)
            trial.set_user_attr("error_traceback", traceback.format_exc())
            return 0.0
        finally:
            # 确保trial输出目录被清理
            if trial_output is not None and trial_output.exists():
                shutil.rmtree(trial_output, ignore_errors=True)

    def _sample_params(self, trial: optuna.Trial) -> Dict[str, Any]:
        """从搜索空间采样参数"""
        ss = self.search_space

        params = {}

        # 模型选择
        if len(ss.model_candidates) > 1:
            params["model"] = trial.suggest_categorical("model", ss.model_candidates)
        else:
            params["model"] = ss.model_candidates[0]

        # 图像尺寸
        imgsz_choices = list(range(ss.imgsz_min, ss.imgsz_max + 1, ss.imgsz_step))
        if len(imgsz_choices) > 1:
            params["imgsz"] = trial.suggest_categorical("imgsz", imgsz_choices)
        else:
            params["imgsz"] = imgsz_choices[0]

        # 批次大小
        batch_choices = list(range(ss.batch_min, ss.batch_max + 1, ss.batch_step))
        if len(batch_choices) > 1:
            params["batch"] = trial.suggest_categorical("batch", batch_choices)
        else:
            params["batch"] = batch_choices[0]

        # 学习率
        params["lr0"] = trial.suggest_float("lr0", ss.lr0_min, ss.lr0_max, log=ss.lr0_log)

        # 优化器
        if len(ss.optimizer_candidates) > 1:
            params["optimizer"] = trial.suggest_categorical("optimizer", ss.optimizer_candidates)
        else:
            params["optimizer"] = ss.optimizer_candidates[0]

        # 学习率调度
        if len(ss.cos_lr_candidates) > 1:
            params["cos_lr"] = trial.suggest_categorical("cos_lr", ss.cos_lr_candidates)
        else:
            params["cos_lr"] = ss.cos_lr_candidates[0]

        # 数据增强
        params["mosaic"] = trial.suggest_float("mosaic", ss.mosaic_min, ss.mosaic_max)
        params["mixup"] = trial.suggest_float("mixup", ss.mixup_min, ss.mixup_max)
        params["degrees"] = trial.suggest_float("degrees", ss.degrees_min, ss.degrees_max)
        params["scale"] = trial.suggest_float("scale", ss.scale_min, ss.scale_max)
        params["translate"] = trial.suggest_float("translate", ss.translate_min, ss.translate_max)
        params["shear"] = trial.suggest_float("shear", ss.shear_min, ss.shear_max)
        params["perspective"] = trial.suggest_float("perspective", ss.perspective_min, ss.perspective_max)
        params["flipud"] = trial.suggest_float("flipud", ss.flipud_min, ss.flipud_max)
        params["hsv_h"] = trial.suggest_float("hsv_h", ss.hsv_h_min, ss.hsv_h_max)
        params["hsv_s"] = trial.suggest_float("hsv_s", ss.hsv_s_min, ss.hsv_s_max)
        params["hsv_v"] = trial.suggest_float("hsv_v", ss.hsv_v_min, ss.hsv_v_max)
        params["copy_paste"] = trial.suggest_float("copy_paste", ss.copy_paste_min, ss.copy_paste_max)
        params["close_mosaic"] = trial.suggest_int("close_mosaic", ss.close_mosaic_min, ss.close_mosaic_max)

        # 正则化
        params["dropout"] = trial.suggest_float("dropout", ss.dropout_min, ss.dropout_max)
        params["label_smoothing"] = trial.suggest_float("label_smoothing", ss.label_smoothing_min, ss.label_smoothing_max)
        params["weight_decay"] = trial.suggest_float("weight_decay", ss.weight_decay_min, ss.weight_decay_max, log=ss.weight_decay_log)
        params["freeze"] = trial.suggest_int("freeze", ss.freeze_min, ss.freeze_max)

        # 损失权重
        params["box"] = trial.suggest_float("box", ss.box_min, ss.box_max)
        params["cls"] = trial.suggest_float("cls", ss.cls_min, ss.cls_max)
        params["dfl"] = trial.suggest_float("dfl", ss.dfl_min, ss.dfl_max)

        return params

    def _extract_metric(self, results: Any, metric: str) -> Optional[float]:
        """从训练结果中提取指标"""
        try:
            if hasattr(results, "results_dict"):
                return results.results_dict.get(metric, 0.0)
            elif hasattr(results, "metrics"):
                metrics = results.metrics
                if isinstance(metrics, dict):
                    return metrics.get(metric, 0.0)
            return 0.0
        except Exception:
            return 0.0

    def _extract_metric_from_dict(self, metrics: Any, metric: str) -> Optional[float]:
        """从指标字典中提取值"""
        try:
            if isinstance(metrics, dict):
                return metrics.get(metric)
            return None
        except Exception:
            return None

    def _save_result(self, result: TuningResult):
        """保存搜索结果"""
        result_path = self.tuning_dir / f"{self.study_name}_result.json"
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)

        # 同时保存为YAML格式便于阅读
        try:
            import yaml
            yaml_path = self.tuning_dir / f"{self.study_name}_best_params.yaml"
            with open(yaml_path, "w", encoding="utf-8") as f:
                yaml.dump(result.best_params, f, allow_unicode=True, sort_keys=False)
        except ImportError:
            pass

    def cleanup(self):
        """清理临时文件"""
        if self._temp_dir_created and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self._temp_dir_created = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False

    def __del__(self):
        self.cleanup()


def quick_tune(
    data_yaml_path: str,
    dataset_name: str,
    n_trials: int = 20,
    metric: str = "metrics/mAP50(B)",
    base_dir: Optional[str] = None,
) -> TuningResult:
    """
    快速超参数搜索便捷函数

    Args:
        data_yaml_path: data.yaml文件路径
        dataset_name: 数据集名称
        n_trials: 搜索轮数
        metric: 优化指标
        base_dir: 项目根目录

    Returns:
        TuningResult对象
    """
    tuner = YOLOHyperparameterTuner(
        data_yaml_path=data_yaml_path,
        base_dir=base_dir,
        study_name=f"{dataset_name}_tuning",
    )

    # 根据数据集大小调整搜索空间
    search_space = SearchSpace()

    result = tuner.tune(
        n_trials=n_trials,
        search_space=search_space,
        metric=metric,
    )

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="YOLO超参数搜索")
    parser.add_argument("data_yaml", help="data.yaml文件路径")
    parser.add_argument("--n-trials", type=int, default=20, help="搜索轮数")
    parser.add_argument("--metric", default="metrics/mAP50(B)", help="优化指标")
    parser.add_argument("--timeout", type=int, default=None, help="超时时间（秒）")
    parser.add_argument("--study-name", default=None, help="Study名称")

    args = parser.parse_args()

    print("=" * 60)
    print("YOLO超参数自动搜索")
    print("=" * 60)
    print(f"数据配置: {args.data_yaml}")
    print(f"搜索轮数: {args.n_trials}")
    print(f"优化指标: {args.metric}")
    print("=" * 60)

    tuner = YOLOHyperparameterTuner(
        data_yaml_path=args.data_yaml,
        study_name=args.study_name,
    )

    result = tuner.tune(
        n_trials=args.n_trials,
        metric=args.metric,
        timeout=args.timeout,
    )

    print("=" * 60)
    print("搜索完成!")
    print(f"最优值: {result.best_value:.4f}")
    print(f"最优参数:")
    for key, value in result.best_params.items():
        print(f"  {key}: {value}")
    print(f"总耗时: {result.duration:.2f}秒")
    print("=" * 60)
