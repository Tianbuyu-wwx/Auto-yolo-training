"""
超参数搜索模块单元测试
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest

from src.hyperparameter_tuning import SearchSpace, TuningResult, _float


class TestHyperparameterTuning(unittest.TestCase):
    """测试超参数搜索模块"""

    def test_search_space_defaults(self):
        """测试搜索空间默认值"""
        space = SearchSpace()
        self.assertIn("yolov8s.pt", space.model_candidates)
        self.assertGreaterEqual(space.batch_min, 1)
        self.assertGreaterEqual(space.batch_max, space.batch_min)
        self.assertTrue(space.lr0_log)

    def test_search_space_custom(self):
        """测试自定义搜索空间"""
        space = SearchSpace(
            model_candidates=["yolov8n.pt"],
            batch_min=2,
            batch_max=8,
            lr0_min=1e-5,
            lr0_max=1e-3,
        )
        self.assertEqual(space.model_candidates, ["yolov8n.pt"])
        self.assertEqual(space.batch_min, 2)
        self.assertEqual(space.batch_max, 8)

    def test_search_space_ranges_defaults(self):
        """阶段 B8：ranges 默认值"""
        space = SearchSpace()
        self.assertIn("imgsz", space.ranges)
        self.assertIn("lr0", space.ranges)

    def test_search_space_add_and_get_range(self):
        """阶段 B8：add_range + get_range"""
        space = SearchSpace()
        space.add_range("custom", _float(0.0, 1.0))
        r = space.get_range("custom")
        self.assertEqual(r.min, 0.0)
        self.assertEqual(r.max, 1.0)

    def test_search_space_to_from_ranges_roundtrip(self):
        """阶段 B8：序列化往返"""
        space = SearchSpace()
        d = space.to_ranges_dict()
        self.assertIn("imgsz", d)
        self.assertEqual(d["imgsz"]["step"], 640)
        reconstructed = SearchSpace.from_ranges_dict(d)
        for name in ("imgsz", "lr0", "batch"):
            self.assertEqual(type(space.get_range(name)), type(reconstructed.get_range(name)))

    def test_tuning_result(self):
        """测试结果数据结构"""
        result = TuningResult(
            best_params={"lr0": 0.001, "batch": 8},
            best_value=0.85,
            n_trials=10,
            study_name="test_study",
            duration=120.0,
        )
        self.assertEqual(result.best_value, 0.85)
        self.assertEqual(result.n_trials, 10)
        self.assertIn("lr0", result.best_params)
        d = result.to_dict()
        self.assertIn("best_params", d)
        self.assertIn("best_value", d)

    def test_search_space_to_dict(self):
        """测试搜索空间转字典"""
        space = SearchSpace()
        d = space.to_dict()
        self.assertIn("model_candidates", d)
        self.assertIn("batch_range", d)
        self.assertIn("lr0_range", d)


if __name__ == "__main__":
    unittest.main()
