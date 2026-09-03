"""
模型评估模块单元测试
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest

from src.evaluator import EvaluationMetrics, EvaluationReport


class TestEvaluator(unittest.TestCase):
    """测试模型评估模块"""

    def test_evaluation_metrics_defaults(self):
        """测试评估指标默认值"""
        metrics = EvaluationMetrics()
        self.assertEqual(metrics.mAP50, 0.0)
        self.assertEqual(metrics.mAP50_95, 0.0)
        self.assertEqual(metrics.precision, 0.0)
        self.assertEqual(metrics.recall, 0.0)

    def test_evaluation_metrics_to_dict(self):
        """测试指标转字典"""
        metrics = EvaluationMetrics(
            mAP50=0.85,
            mAP50_95=0.65,
            precision=0.90,
            recall=0.88,
        )
        d = metrics.to_dict()
        self.assertEqual(d["mAP50"], 0.85)
        self.assertEqual(d["precision"], 0.90)
        self.assertIn("class_metrics", d)

    def test_evaluation_report(self):
        """测试评估报告"""
        metrics = EvaluationMetrics(mAP50=0.9, mAP50_95=0.7)
        report = EvaluationReport(
            model_path="model.pt",
            dataset_name="test",
            data_yaml="data.yaml",
            metrics=metrics,
        )
        self.assertEqual(report.model_path, "model.pt")
        self.assertEqual(report.metrics.mAP50, 0.9)
        d = report.to_dict()
        self.assertIn("timestamp", d)
        self.assertIn("metrics", d)


if __name__ == "__main__":
    unittest.main()
