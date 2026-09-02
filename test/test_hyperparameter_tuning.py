"""
超参数搜索模块单元测试
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
from src.hyperparameter_tuning import SearchSpace, TuningResult


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
