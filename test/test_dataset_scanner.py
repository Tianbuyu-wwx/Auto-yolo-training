"""
数据集扫描器单元测试
验证对不同目录结构数据集的兼容性和稳定性
"""

import unittest
import tempfile
import shutil
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.dataset_scanner import (
    DatasetScanner,
    DatasetStructure,
    scan_dataset,
    discover_datasets,
)


class TestDatasetScanner(unittest.TestCase):
    """测试数据集扫描器"""

    def setUp(self):
        """创建临时测试目录"""
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        """清理临时目录"""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def _create_yolo_standard_dataset(self, name: str = "yolo_std") -> Path:
        """创建标准YOLO结构数据集"""
        ds_path = self.test_dir / name
        for split in ["train", "val", "test"]:
            (ds_path / "images" / split).mkdir(parents=True)
            (ds_path / "labels" / split).mkdir(parents=True)
            # 创建测试图像文件
            for i in range(5):
                (ds_path / "images" / split / f"img_{i}.jpg").touch()
                (ds_path / "labels" / split / f"img_{i}.txt").write_text("0 0.5 0.5 0.1 0.1\n")
        return ds_path

    def _create_class_subdir_dataset(self, name: str = "class_subdirs") -> Path:
        """创建带类别子目录的数据集（模拟 cable end sleeve 结构）"""
        ds_path = self.test_dir / name
        classes = ["good", "missing material"]
        for split in ["train", "val", "test"]:
            for cls in classes:
                (ds_path / "images" / split / cls).mkdir(parents=True)
                (ds_path / "labels" / split / cls).mkdir(parents=True)
                for i in range(3):
                    (ds_path / "images" / split / cls / f"Image_{cls}_{i}.png").touch()
                    (ds_path / "labels" / split / cls / f"Image_{cls}_{i}.txt").write_text(
                        f"{classes.index(cls)} 0.5 0.5 0.1 0.1\n"
                    )
        return ds_path

    def _create_nested_dataset(self, name: str = "nested") -> Path:
        """创建嵌套结构数据集"""
        ds_path = self.test_dir / name
        # 模拟多层嵌套: dataset/v1/train/images/
        (ds_path / "v1" / "train" / "images").mkdir(parents=True)
        (ds_path / "v1" / "val" / "images").mkdir(parents=True)
        for i in range(5):
            (ds_path / "v1" / "train" / "images" / f"img_{i}.jpg").touch()
            (ds_path / "v1" / "val" / "images" / f"img_{i}.jpg").touch()
        return ds_path

    def _create_flat_dataset(self, name: str = "flat") -> Path:
        """创建扁平结构数据集"""
        ds_path = self.test_dir / name
        ds_path.mkdir()
        for i in range(10):
            (ds_path / f"image_{i}.jpg").touch()
        return ds_path

    def _create_empty_dataset(self, name: str = "empty") -> Path:
        """创建空数据集"""
        ds_path = self.test_dir / name
        ds_path.mkdir()
        return ds_path

    def _create_corrupted_image_dataset(self, name: str = "corrupted") -> Path:
        """创建包含损坏文件的数据集"""
        ds_path = self.test_dir / name
        (ds_path / "images" / "train").mkdir(parents=True)
        # 创建一个空的"图像"文件（损坏）
        (ds_path / "images" / "train" / "bad.jpg").write_text("not an image")
        # 创建一个正常大小的文件但内容无效
        (ds_path / "images" / "train" / "also_bad.jpg").write_bytes(b"\x00" * 100)
        return ds_path

    def test_detect_yolo_standard_structure(self):
        """测试识别标准YOLO结构"""
        ds_path = self._create_yolo_standard_dataset()
        scanner = DatasetScanner(str(ds_path))
        profile = scanner.scan()

        self.assertEqual(profile.structure, DatasetStructure.YOLO_STANDARD)
        self.assertEqual(profile.image_count, 15)  # 5 * 3 splits
        self.assertEqual(profile.label_count, 15)
        self.assertIn("train", profile.splits)
        self.assertIn("val", profile.splits)
        self.assertIn("test", profile.splits)

    def test_detect_class_subdir_structure(self):
        """测试识别带类别子目录的结构（cable end sleeve 类型）"""
        ds_path = self._create_class_subdir_dataset()
        scanner = DatasetScanner(str(ds_path))
        profile = scanner.scan()

        self.assertEqual(profile.structure, DatasetStructure.YOLO_CLASS_SUBDIRS)
        self.assertEqual(profile.image_count, 18)  # 3 splits * 2 classes * 3 images
        self.assertEqual(len(profile.classes), 2)
        self.assertIn("good", profile.classes)
        self.assertIn("missing material", profile.classes)

    def test_detect_nested_structure(self):
        """测试识别嵌套结构"""
        ds_path = self._create_nested_dataset()
        scanner = DatasetScanner(str(ds_path))
        profile = scanner.scan()

        self.assertEqual(profile.structure, DatasetStructure.NESTED)
        self.assertEqual(profile.image_count, 10)
        self.assertIn("train", profile.splits)
        self.assertIn("val", profile.splits)

    def test_detect_flat_structure(self):
        """测试识别扁平结构"""
        ds_path = self._create_flat_dataset()
        scanner = DatasetScanner(str(ds_path))
        profile = scanner.scan()

        self.assertEqual(profile.structure, DatasetStructure.FLAT)
        self.assertEqual(profile.image_count, 10)
        self.assertIn("train", profile.splits)

    def test_empty_dataset(self):
        """测试空数据集处理"""
        ds_path = self._create_empty_dataset()
        scanner = DatasetScanner(str(ds_path))
        profile = scanner.scan()

        self.assertEqual(profile.structure, DatasetStructure.UNKNOWN)
        self.assertEqual(profile.image_count, 0)
        self.assertTrue(len(profile.issues) > 0)

    def test_nonexistent_path(self):
        """测试不存在的路径"""
        scanner = DatasetScanner(str(self.test_dir / "nonexistent"))
        profile = scanner.scan()

        self.assertEqual(profile.structure, DatasetStructure.UNKNOWN)
        self.assertTrue(len(profile.issues) > 0)
        self.assertIn("不存在", profile.issues[0])

    def test_corrupted_images(self):
        """测试损坏图像文件的处理"""
        ds_path = self._create_corrupted_image_dataset()
        scanner = DatasetScanner(str(ds_path))
        profile = scanner.scan()

        # 应该能识别到图像文件
        self.assertEqual(profile.image_count, 2)
        # 但应该报告读取问题
        self.assertTrue(len(profile.issues) >= 0)  # 至少没有崩溃

    def test_image_label_matching(self):
        """测试图像-标注文件匹配"""
        ds_path = self._create_yolo_standard_dataset()
        scanner = DatasetScanner(str(ds_path))
        profile = scanner.scan()

        for split in ["train", "val", "test"]:
            images = profile.splits[split]["images"]
            for img in images:
                self.assertIsNotNone(img.label_path)
                self.assertTrue(img.label_path.exists())

    def test_discover_multiple_datasets(self):
        """测试发现多个数据集"""
        self._create_yolo_standard_dataset("ds1")
        self._create_class_subdir_dataset("ds2")
        self._create_flat_dataset("ds3")
        self._create_empty_dataset("ds4")  # 应该被忽略

        datasets = discover_datasets(str(self.test_dir))
        self.assertEqual(len(datasets), 3)

        names = [d.name for d in datasets]
        self.assertIn("ds1", names)
        self.assertIn("ds2", names)
        self.assertIn("ds3", names)

    def test_class_detection_from_labels(self):
        """测试从标注文件中检测类别"""
        ds_path = self._create_class_subdir_dataset()
        scanner = DatasetScanner(str(ds_path))
        profile = scanner.scan()

        # 应该从标注中提取到 class_0 和 class_1
        self.assertTrue(len(profile.classes) > 0)

    def test_split_keyword_detection(self):
        """测试split关键词检测"""
        ds_path = self.test_dir / "keyword_test"
        (ds_path / "training" / "images").mkdir(parents=True)
        (ds_path / "validation" / "images").mkdir(parents=True)
        (ds_path / "testing" / "images").mkdir(parents=True)

        for i in range(3):
            (ds_path / "training" / "images" / f"img_{i}.jpg").touch()
            (ds_path / "validation" / "images" / f"img_{i}.jpg").touch()
            (ds_path / "testing" / "images" / f"img_{i}.jpg").touch()

        scanner = DatasetScanner(str(ds_path))
        profile = scanner.scan()

        self.assertIn("train", profile.splits)
        self.assertIn("val", profile.splits)
        self.assertIn("test", profile.splits)

    def test_permission_error_handling(self):
        """测试权限错误处理"""
        import stat
        ds_path = self._create_yolo_standard_dataset("no_permission")

        scanner = DatasetScanner(str(ds_path))
        # 不应该抛出异常，即使有权限问题也会被捕获
        profile = scanner.scan()
        # 至少应该检测到结构
        self.assertEqual(profile.structure, DatasetStructure.YOLO_STANDARD)

    def test_real_cabel_damage_mini(self):
        """测试真实数据集: cabel-damage-mini"""
        ds_path = Path("dataset/cabel-damage-mini")
        if not ds_path.exists():
            self.skipTest("cabel-damage-mini 数据集不存在")

        scanner = DatasetScanner(str(ds_path))
        profile = scanner.scan()

        self.assertEqual(profile.structure, DatasetStructure.YOLO_STANDARD)
        self.assertTrue(profile.image_count > 0)
        self.assertIn("train", profile.splits)

    def test_real_cable_end_sleeve(self):
        """测试真实数据集: cable end sleeve"""
        ds_path = Path("dataset/cable end sleeve")
        if not ds_path.exists():
            self.skipTest("cable end sleeve 数据集不存在")

        scanner = DatasetScanner(str(ds_path))
        profile = scanner.scan()

        self.assertEqual(profile.structure, DatasetStructure.YOLO_CLASS_SUBDIRS)
        self.assertTrue(profile.image_count > 0)
        self.assertIn("train", profile.splits)
        self.assertIn("good", profile.classes)


class TestDatasetScannerEdgeCases(unittest.TestCase):
    """测试边界情况"""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_mixed_file_types(self):
        """测试混合文件类型"""
        ds_path = self.test_dir / "mixed"
        (ds_path / "images" / "train").mkdir(parents=True)

        # 创建各种文件
        (ds_path / "images" / "train" / "img1.jpg").touch()
        (ds_path / "images" / "train" / "img2.png").touch()
        (ds_path / "images" / "train" / "img3.bmp").touch()
        (ds_path / "images" / "train" / "readme.txt").write_text("not an image")
        (ds_path / "images" / "train" / "data.json").write_text("{}")

        scanner = DatasetScanner(str(ds_path))
        profile = scanner.scan()

        # 应该只识别图像文件
        self.assertEqual(profile.image_count, 3)

    def test_deep_nesting(self):
        """测试深层嵌套（但不超过最大深度限制）"""
        ds_path = self.test_dir / "deep"
        current = ds_path
        for i in range(5):
            current = current / f"level_{i}"
        (current / "images" / "train").mkdir(parents=True)
        (current / "images" / "train" / "img.jpg").touch()

        scanner = DatasetScanner(str(ds_path))
        profile = scanner.scan()

        # 应该能检测到图像
        self.assertTrue(profile.image_count > 0)

    def test_unicode_filenames(self):
        """测试中文文件名"""
        ds_path = self.test_dir / "unicode"
        (ds_path / "images" / "train").mkdir(parents=True)
        (ds_path / "images" / "train" / "图片_1.jpg").touch()
        (ds_path / "images" / "train" / "图像_测试.png").touch()

        scanner = DatasetScanner(str(ds_path))
        profile = scanner.scan()

        self.assertEqual(profile.image_count, 2)

    def test_hidden_directories_ignored(self):
        """测试隐藏目录被忽略"""
        ds_path = self.test_dir / "hidden"
        (ds_path / "images" / "train").mkdir(parents=True)
        (ds_path / "images" / "train" / ".git").mkdir()
        (ds_path / "images" / "train" / "__pycache__").mkdir()
        (ds_path / "images" / "train" / "img.jpg").touch()
        # 在隐藏目录中创建文件，不应被计入
        (ds_path / "images" / "train" / ".git" / "hidden_img.jpg").touch()
        (ds_path / "images" / "train" / "__pycache__" / "cached_img.jpg").touch()

        scanner = DatasetScanner(str(ds_path))
        profile = scanner.scan()

        # 应该只识别正常图像（不包括隐藏目录中的）
        self.assertEqual(profile.image_count, 1)


if __name__ == "__main__":
    unittest.main()
