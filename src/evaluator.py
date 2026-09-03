"""
模型评估自动化模块
自动在测试集上评估模型性能，生成标准化报告
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class EvaluationMetrics:
    """评估指标"""
    mAP50: float = 0.0
    mAP50_95: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    fitness: float = 0.0
    class_metrics: dict[str, dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mAP50": round(self.mAP50, 4),
            "mAP50_95": round(self.mAP50_95, 4),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "fitness": round(self.fitness, 4),
            "class_metrics": self.class_metrics,
        }


@dataclass
class EvaluationReport:
    """评估报告"""
    model_path: str
    dataset_name: str
    data_yaml: str
    metrics: EvaluationMetrics
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    comparison: dict[str, Any] | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_path": self.model_path,
            "dataset_name": self.dataset_name,
            "data_yaml": self.data_yaml,
            "timestamp": self.timestamp,
            "metrics": self.metrics.to_dict(),
            "comparison": self.comparison,
            "details": self.details,
        }


class ModelEvaluator:
    """YOLO模型评估器"""

    def __init__(self, base_dir: str | None = None):
        self.base_dir = Path(base_dir).resolve() if base_dir else Path(__file__).parent.parent.resolve()
        self.reports_dir = self.base_dir / "reports"
        self.reports_dir.mkdir(exist_ok=True)

    def evaluate(
        self,
        model_path: str,
        data_yaml: str,
        dataset_name: str,
        imgsz: int = 640,
        batch: int = 16,
        conf: float = 0.001,
        iou: float = 0.6,
        save_json: bool = True,
        save_plots: bool = True,
        compare_with: str | None = None,
    ) -> EvaluationReport:
        """
        评估模型性能

        Args:
            model_path: 模型文件路径 (.pt)
            data_yaml: 数据集配置文件路径
            dataset_name: 数据集名称
            imgsz: 输入图像尺寸
            batch: 批次大小
            conf: 置信度阈值
            iou: IoU阈值
            save_json: 是否保存JSON报告
            save_plots: 是否保存可视化图表
            compare_with: 与历史结果对比的路径

        Returns:
            EvaluationReport对象
        """
        try:
            from ultralytics import YOLO
        except ImportError as e:
            raise ImportError("未安装ultralytics，无法执行评估") from e

        model_path = Path(model_path).resolve()
        if not model_path.exists():
            raise FileNotFoundError(f"模型文件不存在: {model_path}")

        # 加载模型
        model = YOLO(str(model_path))

        # 执行验证
        results = model.val(
            data=str(Path(data_yaml).resolve()),
            imgsz=imgsz,
            batch=batch,
            conf=conf,
            iou=iou,
            save_json=save_json,
            plots=save_plots,
            project=str(self.base_dir / "runs" / "detect"),
            name=f"{dataset_name}_eval",
            exist_ok=True,
        )

        # 提取指标
        metrics = self._extract_metrics(results)

        # 构建报告
        report = EvaluationReport(
            model_path=str(model_path),
            dataset_name=dataset_name,
            data_yaml=data_yaml,
            metrics=metrics,
        )

        # 与历史结果对比
        if compare_with:
            report.comparison = self._compare_with_history(
                metrics, compare_with, dataset_name
            )

        # 保存报告
        if save_json:
            self._save_report(report)

        return report

    def evaluate_run(
        self,
        run_dir: str,
        data_yaml: str,
        dataset_name: str,
        **kwargs,
    ) -> EvaluationReport:
        """
        评估训练运行目录中的最佳模型

        Args:
            run_dir: 训练运行目录（如 runs/detect/cabel-damage-mini_auto）
            data_yaml: 数据集配置文件
            dataset_name: 数据集名称
            **kwargs: 传递给evaluate的其他参数

        Returns:
            EvaluationReport对象
        """
        run_dir = Path(run_dir)
        best_model = run_dir / "weights" / "best.pt"

        if not best_model.exists():
            raise FileNotFoundError(f"未找到最佳模型: {best_model}")

        return self.evaluate(
            model_path=str(best_model),
            data_yaml=data_yaml,
            dataset_name=dataset_name,
            **kwargs,
        )

    def batch_evaluate(
        self,
        model_paths: list[str],
        data_yaml: str,
        dataset_name: str,
        **kwargs,
    ) -> list[EvaluationReport]:
        """
        批量评估多个模型

        Args:
            model_paths: 模型路径列表
            data_yaml: 数据集配置文件
            dataset_name: 数据集名称
            **kwargs: 传递给evaluate的其他参数

        Returns:
            EvaluationReport列表
        """
        reports = []
        for model_path in model_paths:
            try:
                report = self.evaluate(
                    model_path=model_path,
                    data_yaml=data_yaml,
                    dataset_name=dataset_name,
                    **kwargs,
                )
                reports.append(report)
            except Exception as e:
                print(f"评估模型失败 {model_path}: {e}")

        return reports

    def generate_comparison_report(
        self,
        reports: list[EvaluationReport],
        output_path: str | None = None,
    ) -> str:
        """
        生成模型对比报告

        Args:
            reports: 评估报告列表
            output_path: 输出路径

        Returns:
            报告文件路径
        """
        if not reports:
            raise ValueError("报告列表为空")

        # 按mAP50排序
        sorted_reports = sorted(
            reports,
            key=lambda r: r.metrics.mAP50,
            reverse=True,
        )

        comparison = {
            "timestamp": datetime.now().isoformat(),
            "model_count": len(reports),
            "ranking": [],
        }

        for i, report in enumerate(sorted_reports, 1):
            comparison["ranking"].append({
                "rank": i,
                "model": Path(report.model_path).name,
                "mAP50": report.metrics.mAP50,
                "mAP50_95": report.metrics.mAP50_95,
                "precision": report.metrics.precision,
                "recall": report.metrics.recall,
            })

        # 保存报告
        if output_path is None:
            output_path = self.reports_dir / f"comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        else:
            output_path = Path(output_path)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(comparison, f, indent=2, ensure_ascii=False)

        return str(output_path)

    def _extract_metrics(self, results: Any) -> EvaluationMetrics:
        """从Ultralytics结果中提取指标"""
        metrics = EvaluationMetrics()

        try:
            # 尝试多种方式提取指标
            if hasattr(results, "results_dict"):
                data = results.results_dict
                metrics.mAP50 = data.get("metrics/mAP50(B)", 0.0)
                metrics.mAP50_95 = data.get("metrics/mAP50-95(B)", 0.0)
                metrics.precision = data.get("metrics/precision(B)", 0.0)
                metrics.recall = data.get("metrics/recall(B)", 0.0)
                metrics.fitness = data.get("fitness", 0.0)
            elif hasattr(results, "box"):
                box = results.box
                metrics.mAP50 = getattr(box, "map50", 0.0)
                metrics.mAP50_95 = getattr(box, "map", 0.0)

            # 提取每个类别的指标
            if hasattr(results, "ap") and hasattr(results, "names"):
                class_aps = results.ap
                names = results.names
                for i, name in names.items():
                    if i < len(class_aps):
                        metrics.class_metrics[name] = {
                            "AP50": round(float(class_aps[i][0]), 4) if len(class_aps[i]) > 0 else 0.0,
                            "AP50_95": round(float(class_aps[i].mean()), 4) if hasattr(class_aps[i], 'mean') else 0.0,
                        }

        except Exception as e:
            print(f"提取指标时出错: {e}")

        return metrics

    def _compare_with_history(
        self,
        current_metrics: EvaluationMetrics,
        history_dir: str,
        dataset_name: str,
    ) -> dict[str, Any]:
        """与历史结果对比"""
        history_dir = Path(history_dir)
        if not history_dir.exists():
            return None

        historical_maps = []
        for report_file in history_dir.glob("*_eval_report.json"):
            try:
                with open(report_file, encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("dataset_name") == dataset_name:
                    historical_maps.append(data["metrics"]["mAP50"])
            except Exception:
                continue

        if not historical_maps:
            return None

        best_historical = max(historical_maps)
        improvement = current_metrics.mAP50 - best_historical

        return {
            "best_historical_mAP50": round(best_historical, 4),
            "current_mAP50": round(current_metrics.mAP50, 4),
            "improvement": round(improvement, 4),
            "improved": improvement > 0,
            "historical_count": len(historical_maps),
        }

    def _save_report(self, report: EvaluationReport):
        """保存评估报告"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_name = Path(report.model_path).stem
        report_path = self.reports_dir / f"{report.dataset_name}_{model_name}_eval_{timestamp}.json"

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)


def quick_evaluate(
    model_path: str,
    data_yaml: str,
    dataset_name: str,
    base_dir: str | None = None,
    **kwargs,
) -> EvaluationReport:
    """
    快速评估便捷函数

    Args:
        model_path: 模型文件路径
        data_yaml: 数据集配置文件
        dataset_name: 数据集名称
        base_dir: 项目根目录
        **kwargs: 其他参数

    Returns:
        EvaluationReport对象
    """
    evaluator = ModelEvaluator(base_dir)
    return evaluator.evaluate(
        model_path=model_path,
        data_yaml=data_yaml,
        dataset_name=dataset_name,
        **kwargs,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="YOLO模型评估工具")
    parser.add_argument("model", help="模型文件路径 (.pt)")
    parser.add_argument("data", help="data.yaml路径")
    parser.add_argument("--dataset", default="unknown", help="数据集名称")
    parser.add_argument("--imgsz", type=int, default=640, help="图像尺寸")
    parser.add_argument("--batch", type=int, default=16, help="批次大小")
    parser.add_argument("--conf", type=float, default=0.001, help="置信度阈值")
    parser.add_argument("--iou", type=float, default=0.6, help="IoU阈值")

    args = parser.parse_args()

    print(f"评估模型: {args.model}")
    print(f"数据集: {args.data}")

    report = quick_evaluate(
        model_path=args.model,
        data_yaml=args.data,
        dataset_name=args.dataset,
        imgsz=args.imgsz,
        batch=args.batch,
        conf=args.conf,
        iou=args.iou,
    )

    print("\n评估结果:")
    print(f"  mAP@50: {report.metrics.mAP50:.4f}")
    print(f"  mAP@50-95: {report.metrics.mAP50_95:.4f}")
    print(f"  Precision: {report.metrics.precision:.4f}")
    print(f"  Recall: {report.metrics.recall:.4f}")
    print(f"  Fitness: {report.metrics.fitness:.4f}")

    if report.metrics.class_metrics:
        print("\n各类别指标:")
        for name, metrics in report.metrics.class_metrics.items():
            print(f"  {name}: AP50={metrics.get('AP50', 0):.4f}")
