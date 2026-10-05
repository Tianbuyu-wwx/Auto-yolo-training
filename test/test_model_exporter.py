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

    def test_export_kwargs_filtered_per_format(self):
        """回归：导出参数必须按格式过滤。

        ultralytics 8.3+ 对不支持的参数直接抛错（如 onnx + workspace），
        曾导致 /api/exports 全格式 500（见 e2e-full 全链路）。
        """
        import tempfile
        import types
        from unittest import mock

        calls: dict = {}

        class FakeYOLO:
            def __init__(self, model_path):
                self._model_path = model_path

            def export(self, **kw):
                fmt = kw.pop("format")
                calls[fmt] = kw
                return str(Path(self._model_path).parent / f"fake_{fmt}.onnx")

        with tempfile.TemporaryDirectory() as td:
            model_pt = Path(td) / "best.pt"
            model_pt.write_bytes(b"fake-weights")
            fake_mod = types.SimpleNamespace(YOLO=FakeYOLO)
            with mock.patch.dict(sys.modules, {"ultralytics": fake_mod}):
                from src.model_exporter import ModelExporter

                ModelExporter(base_dir=td).export(
                    model_path=str(model_pt), formats=["onnx", "engine"]
                )

        # onnx：workspace 必须缺席；onnx 专属参数在场
        self.assertNotIn("workspace", calls["onnx"])
        self.assertIn("opset", calls["onnx"])
        self.assertIn("simplify", calls["onnx"])
        # engine：workspace 允许
        self.assertIn("workspace", calls["engine"])


if __name__ == "__main__":
    unittest.main()
