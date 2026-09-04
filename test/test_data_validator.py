"""
数据验证管道单元测试
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import tempfile
import unittest

import yaml

from src.data_validator import (
    Severity,
    ValidationIssue,
    ValidationReport,
    validate_dataset,
)


class TestDataValidator(unittest.TestCase):
    """测试数据验证模块"""

    @classmethod
    def setUpClass(cls):
        # 使用 dummy_dataset fixture（CI 与本地共享，~3 KB 体积）
        cls.dataset_path = Path(__file__).parent.parent / "dataset" / "dummy_dataset"
        cls.test_image = None  # dummy_dataset 是合成图，不再用真实测试图像

    def test_validate_dataset_returns_report(self):
        """测试验证返回报告对象"""
        report = validate_dataset(str(self.dataset_path))
        self.assertIsInstance(report, ValidationReport)
        self.assertEqual(report.dataset_name, "dummy_dataset")

    def test_validation_report_issues(self):
        """测试报告问题记录"""
        report = ValidationReport(
            dataset_name="test",
            dataset_path="/tmp/test",
        )
        self.assertTrue(report.is_valid)
        self.assertEqual(len(report.issues), 0)

        report.add_issue(ValidationIssue(
            severity=Severity.WARNING,
            category="test",
            message="test warning",
        ))
        self.assertTrue(report.is_valid)
        self.assertEqual(len(report.get_warnings()), 1)

        report.add_issue(ValidationIssue(
            severity=Severity.ERROR,
            category="test",
            message="test error",
        ))
        self.assertFalse(report.is_valid)
        self.assertEqual(len(report.get_errors()), 1)

    def test_validate_dataset_stats(self):
        """测试验证报告统计信息"""
        report = validate_dataset(str(self.dataset_path))
        self.assertIn("total_images", report.stats)
        self.assertIn("total_labels", report.stats)
        self.assertGreater(report.stats["total_images"], 0)

    def test_severity_enum(self):
        """测试严重程度枚举"""
        self.assertEqual(Severity.ERROR.value, "error")
        self.assertEqual(Severity.WARNING.value, "warning")
        self.assertEqual(Severity.INFO.value, "info")

    def test_class_consistency_reads_yaml_from_dataset_root(self):
        """A dataset's own data.yaml controls its declared class count."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset_root = Path(temp_dir) / "sample"
            for relative_dir in (
                "images/train", "images/val", "labels/train", "labels/val"
            ):
                (dataset_root / relative_dir).mkdir(parents=True)
            (dataset_root / "labels" / "train" / "sample.txt").write_text(
                "1 0.5 0.5 0.2 0.2\n", encoding="utf-8"
            )
            (dataset_root / "data.yaml").write_text(
                yaml.safe_dump({"path": ".", "train": "images/train", "val": "images/val", "nc": 1, "names": ["only"]}),
                encoding="utf-8",
            )

            report = validate_dataset(str(dataset_root))

            self.assertEqual(report.stats["expected_classes"], 1)
            self.assertEqual(report.stats["class_names"], ["only"])
            self.assertTrue(any(
                issue.category == "class_mismatch" for issue in report.get_errors()
            ))


if __name__ == "__main__":
    unittest.main()
