"""
模型下载器测试（阶段 C5）

覆盖：
- get_model_path / is_model_downloaded 路径与存在性检查
- move_cached_model 从缓存位置移动到 basemodels/
- ensure_model 幂等：已存在 → 不下载；缓存中 → move；都不在 → FileNotFoundError
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.model_downloader import (
    ensure_model,
    get_model_path,
    is_model_downloaded,
    move_cached_model,
)


class TestGetModelPath(unittest.TestCase):
    """get_model_path 返回 basemodels/ 下的绝对路径"""

    def test_returns_correct_path(self):
        path = get_model_path("yolov8n.pt", "/tmp/project")
        self.assertEqual(path, Path("/tmp/project/basemodels/yolov8n.pt"))


class TestIsModelDownloaded(unittest.TestCase):
    """is_model_downloaded 检查文件存在性"""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        (self.temp_dir / "basemodels").mkdir()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_returns_false_for_missing(self):
        self.assertFalse(is_model_downloaded("yolov8n.pt", self.temp_dir))

    def test_returns_true_for_existing(self):
        (self.temp_dir / "basemodels" / "yolov8n.pt").write_bytes(b"")
        self.assertTrue(is_model_downloaded("yolov8n.pt", self.temp_dir))


class TestMoveCachedModel(unittest.TestCase):
    """move_cached_model 从 Ultralytics 缓存位置移动到 basemodels/"""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        (self.temp_dir / "basemodels").mkdir()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_moves_from_project_ultralytics_dir(self):
        cache = self.temp_dir / "Ultralytics" / "weights"
        cache.mkdir(parents=True)
        src = cache / "yolov8n.pt"
        src.write_bytes(b"fake weights")

        result = move_cached_model("yolov8n.pt", self.temp_dir)
        self.assertEqual(result, self.temp_dir / "basemodels" / "yolov8n.pt")
        self.assertTrue(result.exists())
        self.assertFalse(src.exists())

    def test_returns_none_when_no_cache(self):
        result = move_cached_model("yolov8n.pt", self.temp_dir)
        self.assertIsNone(result)


class TestEnsureModel(unittest.TestCase):
    """ensure_model 幂等：已存在直接返回，否则尝试下载"""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        (self.temp_dir / "basemodels").mkdir()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_returns_existing_model_without_download(self):
        """模型已存在 → 直接返回，不调用任何下载逻辑"""
        existing = self.temp_dir / "basemodels" / "yolov8n.pt"
        existing.write_bytes(b"")

        with patch("src.model_downloader.move_cached_model") as mock_move:
            # 模拟 ultralytics.YOLO 永远不被 import 调用
            with patch.dict("sys.modules", {"ultralytics": None}):
                with patch("builtins.__import__", side_effect=ImportError):
                    result = ensure_model("yolov8n.pt", self.temp_dir)
                    self.assertEqual(result, existing)
                    mock_move.assert_not_called()

    def test_moves_from_cache_when_present(self):
        """缓存中有 → move 到 basemodels/，不触发 Ultralytics 下载"""
        cache = self.temp_dir / "Ultralytics" / "weights"
        cache.mkdir(parents=True)
        (cache / "yolov8n.pt").write_bytes(b"cached weights")

        result = ensure_model("yolov8n.pt", self.temp_dir)
        self.assertEqual(result, self.temp_dir / "basemodels" / "yolov8n.pt")

    def test_raises_when_download_fails(self):
        """缓存和 basemodels 都无，且 ultralytics 调用失败 → FileNotFoundError"""
        # 用 dummy module 替换 ultralytics，让 YOLO() 构造抛错
        import sys
        import types

        dummy = types.ModuleType("ultralytics")
        dummy.YOLO = lambda *a, **kw: (_ for _ in ()).throw(Exception("network error"))
        sys.modules["ultralytics"] = dummy
        try:
            with patch("src.model_downloader.move_cached_model", return_value=None):
                with self.assertRaises(FileNotFoundError) as ctx:
                    ensure_model("yolov8n.pt", self.temp_dir)
                self.assertIn("yolov8n.pt", str(ctx.exception))
        finally:
            del sys.modules["ultralytics"]

    def test_raises_when_ultralytics_not_installed(self):
        """未装 ultralytics → FileNotFoundError 给出明确指引"""
        with patch("src.model_downloader.move_cached_model", return_value=None):
            with patch.dict("sys.modules", {"ultralytics": None}):
                with patch("builtins.__import__", side_effect=ImportError("ultralytics")):
                    with self.assertRaises(FileNotFoundError) as ctx:
                        ensure_model("yolov8n.pt", self.temp_dir)
                    self.assertIn("manually place", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
