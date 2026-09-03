"""
模型清单测试（阶段 C2 + C3）
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.model_catalog import (
    MODEL_CATALOG,
    LocalModelStatus,
    ModelEntry,
    ModelFamily,
    check_local_models,
    model_filename_to_family_dict,
    resolve_model_family,
    suggest_download,
)


class TestResolveModelFamily(unittest.TestCase):
    """文件名 → 家族推断"""

    def test_yolov8s(self):
        self.assertEqual(resolve_model_family("yolov8s.pt"), ModelFamily.YOLOV8)

    def test_yolo11n_seg(self):
        self.assertEqual(resolve_model_family("yolo11n-seg.pt"), ModelFamily.YOLOV11)

    def test_yolo26x_p(self):
        """姿态估计任务也属于 YOLO26"""
        self.assertEqual(resolve_model_family("yolo26x-pose.pt"), ModelFamily.YOLO26)

    def test_yolov8_pose(self):
        self.assertEqual(resolve_model_family("yolov8n-pose.pt"), ModelFamily.YOLOV8)

    def test_unknown_returns_unknown(self):
        self.assertEqual(resolve_model_family("my_custom_model.pt"), ModelFamily.UNKNOWN)

    def test_path_object_accepted(self):
        self.assertEqual(resolve_model_family(Path("/tmp/yolov8s.pt")), ModelFamily.YOLOV8)

    def test_case_insensitive(self):
        self.assertEqual(resolve_model_family("YOLOV8S.PT"), ModelFamily.YOLOV8)


class TestModelCatalog(unittest.TestCase):
    """MODEL_CATALOG 字典覆盖"""

    def test_catalog_includes_yolov5_8_11_26(self):
        """4 个家族都至少有一个条目"""
        families = {e.family for e in MODEL_CATALOG.values()}
        self.assertIn(ModelFamily.YOLOV5, families)
        self.assertIn(ModelFamily.YOLOV8, families)
        self.assertIn(ModelFamily.YOLOV11, families)
        self.assertIn(ModelFamily.YOLO26, families)

    def test_catalog_includes_segment_pose_classify(self):
        """3 个非 detect 任务都覆盖"""
        tasks = {e.task for e in MODEL_CATALOG.values()}
        self.assertIn("segment", tasks)
        self.assertIn("pose", tasks)
        self.assertIn("classify", tasks)

    def test_all_entries_have_unique_filename(self):
        filenames = list(MODEL_CATALOG.keys())
        self.assertEqual(len(filenames), len(set(filenames)))

    def test_download_url_format(self):
        """下载 URL 指向 Ultralytics 官方 release"""
        entry = MODEL_CATALOG["yolov8s.pt"]
        self.assertIn("ultralytics", entry.download_url.lower())
        self.assertTrue(entry.download_url.endswith("yolov8s.pt"))


class TestCheckLocalModels(unittest.TestCase):
    """本地 basemodels/ 扫描"""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_empty_directory(self):
        status = check_local_models(self.temp_dir)
        self.assertEqual(status.available, [])
        self.assertEqual(status.total_size_mb, 0.0)
        self.assertGreater(len(status.missing_popular), 0)

    def test_with_one_model(self):
        # 创建伪 yolov8s.pt
        fake = self.temp_dir / "yolov8s.pt"
        fake.write_bytes(b"x" * (10 * 1024 * 1024))  # 10 MB

        status = check_local_models(self.temp_dir)
        self.assertEqual(len(status.available), 1)
        self.assertEqual(status.available[0].name, "yolov8s.pt")
        # yolov8s.pt 在 size=["n","s"] 范围内，应该从 missing_popular 移除
        missing_filenames = [e.filename for e in status.missing_popular]
        self.assertNotIn("yolov8s.pt", missing_filenames)

    def test_include_sizes_filter(self):
        """include_sizes 参数控制检查范围"""
        fake = self.temp_dir / "yolov8n.pt"
        fake.write_bytes(b"x" * 1024)

        # 默认 size=["n","s"]，yolov8n.pt 在范围内
        status_default = check_local_models(self.temp_dir)
        self.assertNotIn("yolov8n.pt", [e.filename for e in status_default.missing_popular])

        # include_sizes=["x"]，yolov8n.pt 不在范围内但仍会出现在 missing（因为 include 只控制范围，size filter 默认检查）
        # 此处测试扩展到 m/l/x 时，yolov8n 不在 missing_popular（因为已下载）
        status_extended = check_local_models(self.temp_dir, include_sizes=["n", "s", "m", "l", "x"])
        self.assertNotIn("yolov8n.pt", [e.filename for e in status_extended.missing_popular])

    def test_summary_format(self):
        status = check_local_models(self.temp_dir)
        d = status.summary()
        self.assertIn("available_count", d)
        self.assertIn("missing_popular_count", d)
        self.assertIn("total_size_mb", d)


class TestSuggestDownload(unittest.TestCase):
    """suggest_download 命令生成"""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_returns_curl_commands(self):
        entries = [MODEL_CATALOG["yolov8n.pt"], MODEL_CATALOG["yolo26n.pt"]]
        commands = suggest_download(entries)
        # 每条命令 3 行（注释 + curl + 空行）
        self.assertEqual(len(commands), 6)
        # 第一条是 yolov8n.pt 的注释
        self.assertIn("yolov8n.pt", commands[0])
        self.assertIn("yolov8", commands[0])
        # 第二条是 curl
        self.assertIn("curl", commands[1])
        self.assertIn("yolov8n.pt", commands[1])

    def test_custom_target_dir(self):
        entries = [MODEL_CATALOG["yolo11n.pt"]]
        target = self.temp_dir / "custom_models"
        commands = suggest_download(entries, basemodels_dir=target)
        # 自定义目录会被创建
        self.assertTrue(target.exists())
        # curl 命令应包含目标文件名
        joined = "\n".join(commands)
        self.assertIn("yolo11n.pt", joined)
        # 路径片段应出现在 curl 命令中（无论正反斜杠）
        path_parts = str(target).replace("\\", "/").split("/")
        self.assertTrue(any(part in joined for part in path_parts if part))


class TestModelFilenameToFamilyDict(unittest.TestCase):
    """批量推断"""

    def test_batch_inference(self):
        filenames = ["yolov8s.pt", "yolo26n.pt", "yolo11m-seg.pt", "unknown.pt"]
        result = model_filename_to_family_dict(filenames)
        self.assertEqual(result["yolov8s.pt"], ModelFamily.YOLOV8)
        self.assertEqual(result["yolo26n.pt"], ModelFamily.YOLO26)
        self.assertEqual(result["yolo11m-seg.pt"], ModelFamily.YOLOV11)
        self.assertEqual(result["unknown.pt"], ModelFamily.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
