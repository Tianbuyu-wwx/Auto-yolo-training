"""
任务感知评估指标测试（阶段 C6）

覆盖：
- task_metrics_keys 返回正确的指标键（按 task 不同）
- task_metric_label 把 Ultralytics 键转为可读标签
- extract_task_metrics 从 results.results_dict / results.metrics 提取
"""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.task_metrics import (
    extract_task_metrics,
    task_metric_label,
    task_metrics_keys,
)
from src.task_types import TaskType


class TestTaskMetricsKeys(unittest.TestCase):
    """每个任务有正确的指标键"""

    def test_detect_keys(self):
        keys = task_metrics_keys(TaskType.DETECT)
        self.assertIn("metrics/mAP50(B)", keys)
        self.assertIn("metrics/mAP50-95(B)", keys)
        self.assertIn("metrics/precision(B)", keys)
        self.assertIn("metrics/recall(B)", keys)

    def test_segment_keys(self):
        keys = task_metrics_keys(TaskType.SEGMENT)
        self.assertIn("metrics/mAP50(M)", keys)
        self.assertIn("metrics/mAP50-95(M)", keys)
        # segment 不应有 detect 的 (B) 后缀
        self.assertNotIn("metrics/mAP50(B)", keys)

    def test_pose_keys(self):
        keys = task_metrics_keys(TaskType.POSE)
        self.assertIn("metrics/mAP50(P)", keys)
        self.assertIn("metrics/mAP50-95(P)", keys)

    def test_classify_keys(self):
        keys = task_metrics_keys(TaskType.CLASSIFY)
        self.assertIn("metrics/accuracy_top1", keys)
        self.assertIn("metrics/accuracy_top5", keys)

    def test_string_input(self):
        keys = task_metrics_keys("classify")
        self.assertIn("metrics/accuracy_top1", keys)


class TestTaskMetricLabel(unittest.TestCase):
    """Ultralytics 指标键 → 人类可读标签"""

    def test_known_keys(self):
        self.assertEqual(task_metric_label("metrics/mAP50(B)"), "mAP@50")
        self.assertEqual(task_metric_label("metrics/mAP50-95(B)"), "mAP@50-95")
        self.assertEqual(task_metric_label("metrics/precision(B)"), "Precision")
        self.assertEqual(task_metric_label("metrics/accuracy_top1"), "Accuracy@1")

    def test_unknown_key_returns_unchanged(self):
        self.assertEqual(task_metric_label("metrics/custom_thing"), "metrics/custom_thing")


class TestExtractTaskMetrics(unittest.TestCase):
    """extract_task_metrics 从 Ultralytics results 提取指标"""

    def test_extract_from_results_dict(self):
        results = SimpleNamespace(
            results_dict={
                "metrics/mAP50(B)": 0.85,
                "metrics/mAP50-95(B)": 0.42,
                "metrics/precision(B)": 0.78,
                "metrics/recall(B)": 0.65,
                "fitness": 0.55,
            }
        )
        extracted = extract_task_metrics(results, TaskType.DETECT)
        self.assertEqual(extracted["mAP@50"], 0.85)
        self.assertEqual(extracted["mAP@50-95"], 0.42)
        self.assertEqual(extracted["Precision"], 0.78)
        self.assertEqual(extracted["Recall"], 0.65)
        # fitness 不是 detect 指标 → 不应出现
        self.assertNotIn("fitness", extracted)

    def test_extract_from_metrics_dict(self):
        results = SimpleNamespace(
            metrics={
                "metrics/accuracy_top1": 0.92,
                "metrics/accuracy_top5": 0.99,
            }
        )
        extracted = extract_task_metrics(results, TaskType.CLASSIFY)
        self.assertEqual(extracted["Accuracy@1"], 0.92)
        self.assertEqual(extracted["Accuracy@5"], 0.99)

    def test_skips_missing_keys(self):
        results = SimpleNamespace(
            results_dict={
                "metrics/mAP50(B)": 0.85,
                # mAP50-95(B) 缺失
            }
        )
        extracted = extract_task_metrics(results, TaskType.DETECT)
        self.assertEqual(extracted["mAP@50"], 0.85)
        self.assertNotIn("mAP@50-95", extracted)

    def test_skips_non_numeric_values(self):
        results = SimpleNamespace(
            results_dict={
                "metrics/mAP50(B)": "invalid",  # 非数字
                "metrics/mAP50-95(B)": 0.42,
            }
        )
        extracted = extract_task_metrics(results, TaskType.DETECT)
        self.assertNotIn("mAP@50", extracted)
        self.assertEqual(extracted["mAP@50-95"], 0.42)

    def test_empty_results(self):
        results = SimpleNamespace(results_dict={})
        self.assertEqual(extract_task_metrics(results, TaskType.DETECT), {})

    def test_no_results_dict_attribute(self):
        results = SimpleNamespace(other_attr=123)
        self.assertEqual(extract_task_metrics(results, TaskType.DETECT), {})


if __name__ == "__main__":
    unittest.main()
