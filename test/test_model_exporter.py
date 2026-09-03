"""
模型导出模块单元测试
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest

from src.model_exporter import ExportReport, ExportResult


class TestModelExporter(unittest.TestCase):
    """测试模型导出模块"""

    def test_export_result(self):
        """测试导出结果"""
        result = ExportResult(
            format="onnx",
            success=True,
            output_path="model.onnx",
            file_size=1024 * 1024 * 10,
            message="OK",
            duration=5.0,
        )
        d = result.to_dict()
        self.assertEqual(d["format"], "onnx")
        self.assertTrue(d["success"])
        self.assertEqual(d["file_size_mb"], 10.0)

    def test_export_report(self):
        """测试导出报告"""
        report = ExportReport(model_path="model.pt")
        self.assertEqual(report.success_count, 0)
        self.assertEqual(report.total_count, 0)

        report.results.append(ExportResult(format="onnx", success=True))
        report.results.append(ExportResult(format="engine", success=False))
        self.assertEqual(report.success_count, 1)
        self.assertEqual(report.total_count, 2)

    def test_export_report_to_dict(self):
        """测试导出报告转字典"""
        report = ExportReport(model_path="model.pt")
        report.results.append(ExportResult(format="onnx", success=True))
        d = report.to_dict()
        self.assertIn("model_path", d)
        self.assertIn("results", d)
        self.assertEqual(len(d["results"]), 1)


if __name__ == "__main__":
    unittest.main()
