"""
模型版本管理模块单元测试
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import shutil
import tempfile
import unittest

from src.model_registry import ModelRegistry, ModelVersion


class TestModelRegistry(unittest.TestCase):
    """测试模型版本管理模块"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.registry = ModelRegistry(base_dir=self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_model_version_to_dict(self):
        """测试版本信息转字典"""
        version = ModelVersion(
            version_id="v1",
            model_path="model.pt",
            dataset_name="test",
            created_at="2024-01-01T00:00:00",
            metrics={"mAP50": 0.9},
            tags=["production"],
        )
        d = version.to_dict()
        self.assertEqual(d["version_id"], "v1")
        self.assertEqual(d["metrics"]["mAP50"], 0.9)

    def test_registry_init(self):
        """测试注册表初始化"""
        self.assertTrue(self.registry.registry_dir.exists())
        self.assertTrue(self.registry.models_dir.exists())

    def test_register_model(self):
        """测试模型注册"""
        dummy_model = Path(self.tmpdir) / "dummy.pt"
        dummy_model.write_text("dummy")
        version = self.registry.register(
            model_path=str(dummy_model),
            dataset_name="test-dataset",
            metrics={"mAP50": 0.85},
            tags=["test"],
        )
        self.assertIsNotNone(version.version_id)
        self.assertEqual(version.dataset_name, "test-dataset")

    def test_get_versions(self):
        """测试获取版本列表"""
        versions = self.registry.get_versions("test-dataset")
        self.assertIsInstance(versions, list)

    def test_get_version(self):
        """测试获取特定版本"""
        v = self.registry.get_version("nonexistent", "v1")
        self.assertIsNone(v)

    def test_get_latest(self):
        """测试获取最新版本"""
        latest = self.registry.get_latest("nonexistent")
        self.assertIsNone(latest)

    def test_get_best(self):
        """测试获取最佳版本"""
        best = self.registry.get_best("nonexistent")
        self.assertIsNone(best)

    def test_update_status(self):
        """测试更新状态"""
        dummy_model = Path(self.tmpdir) / "dummy.pt"
        dummy_model.write_text("dummy")
        version = self.registry.register(
            model_path=str(dummy_model),
            dataset_name="test-dataset",
        )
        success = self.registry.update_status("test-dataset", version.version_id, "production")
        self.assertTrue(success)

    def test_compare_versions(self):
        """测试版本对比"""
        result = self.registry.compare_versions("test", "v1", "v2")
        self.assertIn("error", result)

    def test_list_all(self):
        """测试列出所有模型"""
        all_models = self.registry.list_all()
        self.assertIsInstance(all_models, dict)

    def test_same_second_registrations_get_distinct_ids(self):
        """时间戳只精确到秒，模型名又都是 best/last：同一秒注册多次不能撞 id。

        撞了会共用 models/<id>/ 副本目录，而 delete_version 是按 id 过滤的，
        一次删除会连带删掉另一条记录。

        时钟必须冻结：不冻结的话两次调用横跨秒边界就自然拿到不同 id，
        测试会「通过但不是因为修好了」。
        """
        from datetime import datetime as real_datetime
        from unittest import mock

        class _FrozenDatetime(real_datetime):
            @classmethod
            def now(cls):
                return real_datetime(2026, 1, 1, 0, 0, 0)

        dummy = Path(self.tmpdir) / "best.pt"
        dummy.write_text("dummy")
        with mock.patch("src.model_registry.datetime", _FrozenDatetime):
            v1 = self.registry.register(model_path=str(dummy), dataset_name="ds")
            v2 = self.registry.register(model_path=str(dummy), dataset_name="ds")

        # 两次的 created_at 完全相同 —— 证明确实落在同一秒
        self.assertEqual(v1.created_at, v2.created_at)
        self.assertNotEqual(v1.version_id, v2.version_id)
        self.assertNotEqual(v1.model_path, v2.model_path)
        self.assertTrue(Path(v1.model_path).is_file())
        self.assertTrue(Path(v2.model_path).is_file())

    def test_delete_version_removes_the_copy_only(self):
        """删版本删的是注册表内的副本，源文件不动"""
        src = Path(self.tmpdir) / "best.pt"
        src.write_text("dummy")
        v = self.registry.register(model_path=str(src), dataset_name="ds")
        copy_path = Path(v.model_path)
        self.assertTrue(copy_path.is_file())

        self.assertTrue(self.registry.delete_version("ds", v.version_id))
        self.assertFalse(copy_path.exists())
        self.assertTrue(src.is_file())


if __name__ == "__main__":
    unittest.main()
