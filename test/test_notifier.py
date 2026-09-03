"""
通知模块单元测试
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import tempfile
import unittest

from src.notifier import (
    ConsoleNotifier,
    FileNotifier,
    NotificationLevel,
    NotificationMessage,
    NotifierManager,
)


class TestNotifier(unittest.TestCase):
    """测试通知模块"""

    def test_notification_level(self):
        """测试通知级别枚举"""
        self.assertEqual(NotificationLevel.INFO.value, "info")
        self.assertEqual(NotificationLevel.SUCCESS.value, "success")
        self.assertEqual(NotificationLevel.WARNING.value, "warning")
        self.assertEqual(NotificationLevel.ERROR.value, "error")

    def test_notification_message(self):
        """测试通知消息"""
        msg = NotificationMessage(
            title="Test",
            content="Test content",
            level=NotificationLevel.SUCCESS,
        )
        d = msg.to_dict()
        self.assertEqual(d["title"], "Test")
        self.assertEqual(d["level"], "success")
        self.assertIn("timestamp", d)

    def test_console_notifier(self):
        """测试控制台通知器"""
        notifier = ConsoleNotifier()
        msg = NotificationMessage(title="Test", content="Hello")
        result = notifier.send(msg)
        self.assertTrue(result)

    def test_file_notifier(self):
        """测试文件通知器"""
        tmpdir = tempfile.mkdtemp()
        try:
            notifier = FileNotifier(log_dir=tmpdir)
            msg = NotificationMessage(title="Test", content="Hello")
            result = notifier.send(msg)
            self.assertTrue(result)
            log_file = Path(tmpdir) / "notifications.jsonl"
            self.assertTrue(log_file.exists())
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_notifier_manager(self):
        """测试通知管理器"""
        manager = NotifierManager()
        results = manager.notify("Test", "Hello", NotificationLevel.INFO)
        self.assertIsInstance(results, list)
        self.assertTrue(all(results))

    def test_notify_training_start(self):
        """测试训练开始通知"""
        manager = NotifierManager()
        results = manager.notify_training_start("test", {"model": "yolov8s.pt"})
        self.assertIsInstance(results, list)

    def test_notify_training_complete(self):
        """测试训练完成通知"""
        manager = NotifierManager()
        results = manager.notify_training_complete(
            "test", {"mAP50": 0.9}, 3600.0
        )
        self.assertIsInstance(results, list)


if __name__ == "__main__":
    unittest.main()
