"""
任务类型抽象测试（阶段 C1）

覆盖：
- TaskType 枚举与 Ultralytics 字符串值对齐
- TaskSpec 默认配置正确（imgsz / label format）
- get_task_spec 接受字符串和枚举
- model_name_for_task 构造正确模型名
- ValueError for invalid task string
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.task_types import (
    TASK_SPECS,
    TaskSpec,
    TaskType,
    get_task_spec,
    model_name_for_task,
)


class TestTaskTypeEnum(unittest.TestCase):
    """TaskType 枚举必须与 Ultralytics YOLO(task=...) 字段严格对齐"""

    def test_string_values_match_ultralytics(self):
        # Ultralytics YOLO(task="detect") 接受这些字符串
        self.assertEqual(TaskType.DETECT.value, "detect")
        self.assertEqual(TaskType.SEGMENT.value, "segment")
        self.assertEqual(TaskType.POSE.value, "pose")
        self.assertEqual(TaskType.CLASSIFY.value, "classify")
        self.assertEqual(TaskType.OBB.value, "obb")

    def test_task_type_is_string_enum(self):
        # str, Enum 双继承 → 可以直接当字符串用
        self.assertEqual(TaskType.DETECT, "detect")
        self.assertTrue(isinstance(TaskType.DETECT, str))


class TestTaskSpec(unittest.TestCase):
    """TaskSpec 提供每种任务的默认配置"""

    def test_all_task_types_have_spec(self):
        for task in TaskType:
            self.assertIn(task, TASK_SPECS)
            self.assertIsInstance(TASK_SPECS[task], TaskSpec)

    def test_detect_default_imgsz(self):
        spec = get_task_spec("detect")
        self.assertEqual(spec.default_imgsz, 640)

    def test_classify_default_imgsz_is_224(self):
        spec = get_task_spec("classify")
        self.assertEqual(spec.default_imgsz, 224)

    def test_supports_bbox_for_object_tasks(self):
        self.assertTrue(get_task_spec("detect").supports_bbox)
        self.assertTrue(get_task_spec("segment").supports_bbox)
        self.assertTrue(get_task_spec("obb").supports_bbox)
        self.assertFalse(get_task_spec("classify").supports_bbox)
        self.assertFalse(get_task_spec("pose").supports_bbox)

    def test_supports_keypoints_only_pose(self):
        self.assertTrue(get_task_spec("pose").supports_keypoints)
        for task in ("detect", "segment", "classify", "obb"):
            self.assertFalse(get_task_spec(task).supports_keypoints)


class TestGetTaskSpec(unittest.TestCase):
    """get_task_spec 同时接受枚举和字符串"""

    def test_with_enum(self):
        spec = get_task_spec(TaskType.DETECT)
        self.assertEqual(spec.task, TaskType.DETECT)

    def test_with_string(self):
        spec = get_task_spec("segment")
        self.assertEqual(spec.task, TaskType.SEGMENT)

    def test_invalid_string_raises(self):
        with self.assertRaises(ValueError) as ctx:
            get_task_spec("unknown_task")
        self.assertIn("不支持的任务类型", str(ctx.exception))
        self.assertIn("detect", str(ctx.exception))


class TestModelNameForTask(unittest.TestCase):
    """model_name_for_task 根据任务+size 构造正确的模型文件名"""

    def test_detect_nano(self):
        self.assertEqual(model_name_for_task("detect", "n"), "yolov8n.pt")

    def test_segment_small(self):
        self.assertEqual(model_name_for_task("segment", "s"), "yolov8s-seg.pt")

    def test_classify_medium(self):
        self.assertEqual(model_name_for_task("classify", "m"), "yolov8m-cls.pt")

    def test_pose_large(self):
        self.assertEqual(model_name_for_task("pose", "l"), "yolov8l-pose.pt")

    def test_obb_nano(self):
        self.assertEqual(model_name_for_task("obb", "n"), "yolov8n-obb.pt")

    def test_default_size_is_nano(self):
        self.assertEqual(model_name_for_task("detect"), "yolov8n.pt")
        self.assertEqual(model_name_for_task("classify"), "yolov8n-cls.pt")

    def test_with_enum_input(self):
        self.assertEqual(
            model_name_for_task(TaskType.SEGMENT, "n"),
            "yolov8n-seg.pt",
        )


if __name__ == "__main__":
    unittest.main()
