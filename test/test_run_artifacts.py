"""
训练产物解析测试（阶段 C7）
"""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.run_artifacts import (
    find_latest_run,
    list_run_artifacts,
    parse_results_csv,
)


class TestFindLatestRun(unittest.TestCase):
    """find_latest_run 找到最近一次训练运行"""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.runs_dir = self.temp_dir / "runs" / "detect"
        self.runs_dir.mkdir(parents=True)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_returns_none_for_empty_dir(self):
        self.assertIsNone(find_latest_run("my_dataset", self.temp_dir))

    def test_returns_none_for_no_runs_dir(self):
        empty = Path(tempfile.mkdtemp())
        try:
            self.assertIsNone(find_latest_run("my_dataset", empty))
        finally:
            import shutil
            shutil.rmtree(empty, ignore_errors=True)

    def test_finds_only_matching_dataset(self):
        # 创建一个匹配 + 一个不匹配的
        (self.runs_dir / "my_dataset_v1").mkdir()
        (self.runs_dir / "my_dataset_v2").mkdir()
        (self.runs_dir / "other_dataset").mkdir()

        latest = find_latest_run("my_dataset", self.temp_dir)
        self.assertIsNotNone(latest)
        self.assertIn("my_dataset", latest.name)
        self.assertNotIn("other_dataset", latest.name)

    def test_returns_most_recent(self):
        import os
        import time

        old_dir = self.runs_dir / "my_dataset_old"
        new_dir = self.runs_dir / "my_dataset_new"
        old_dir.mkdir()
        new_dir.mkdir()
        # 设置不同 mtime
        os.utime(old_dir, (1000000000, 1000000000))
        time.sleep(0.1)
        os.utime(new_dir, (2000000000, 2000000000))

        latest = find_latest_run("my_dataset", self.temp_dir)
        self.assertEqual(latest.name, "my_dataset_new")


class TestListRunArtifacts(unittest.TestCase):
    """list_run_artifacts 列出运行产出的所有可视化文件"""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_missing_files_returns_empty(self):
        artifacts = list_run_artifacts(self.temp_dir)
        self.assertEqual(artifacts.run_dir, self.temp_dir)
        self.assertIsNone(artifacts.csv_path)
        self.assertEqual(artifacts.plots, [])
        self.assertFalse(artifacts.has_results_csv)

    def test_lists_existing_artifacts(self):
        # 创建一些文件
        (self.temp_dir / "results.csv").write_text("epoch,loss\n1,0.5\n")
        (self.temp_dir / "results.png").write_bytes(b"")
        (self.temp_dir / "confusion_matrix_normalized.png").write_bytes(b"")
        # 不应识别的文件
        (self.temp_dir / "weights").mkdir()
        (self.temp_dir / "best.pt").write_bytes(b"")

        artifacts = list_run_artifacts(self.temp_dir)
        self.assertTrue(artifacts.has_results_csv)
        plot_names = {p.name for p in artifacts.plots}
        self.assertIn("results.png", plot_names)
        self.assertIn("confusion_matrix_normalized.png", plot_names)
        self.assertNotIn("best.pt", plot_names)


class TestParseResultsCsv(unittest.TestCase):
    """parse_results_csv 解析 results.csv 为 list of dict"""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_missing_csv_returns_empty(self):
        self.assertEqual(parse_results_csv(self.temp_dir), [])

    def test_parse_basic_csv(self):
        csv_path = self.temp_dir / "results.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["epoch", "train/loss", "metrics/mAP50(B)"])
            writer.writeheader()
            writer.writerow({"epoch": "0", "train/loss": "1.5", "metrics/mAP50(B)": "0.0"})
            writer.writerow({"epoch": "1", "train/loss": "1.0", "metrics/mAP50(B)": "0.3"})

        rows = parse_results_csv(self.temp_dir)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["epoch"], "0")
        self.assertEqual(rows[1]["metrics/mAP50(B)"], "0.3")

    def test_handles_whitespace_in_keys(self):
        csv_path = self.temp_dir / "results.csv"
        # Ultralytics 有时写 " epoch" 带前导空格
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write(" epoch , loss\n0, 0.5\n")

        rows = parse_results_csv(self.temp_dir)
        self.assertEqual(rows[0]["epoch"], "0")  # 已 strip

    def test_empty_csv_returns_empty(self):
        csv_path = self.temp_dir / "results.csv"
        csv_path.write_text("", encoding="utf-8")
        self.assertEqual(parse_results_csv(self.temp_dir), [])


if __name__ == "__main__":
    unittest.main()
