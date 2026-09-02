"""
日志捕获与管理服务
"""

import sys
import logging
from collections import deque
from typing import Optional


logger = logging.getLogger(__name__)


class QueueLogHandler(logging.Handler):
    """将日志写入队列的Handler，过滤重复pynvml警告"""

    def __init__(self, log_queue: deque):
        super().__init__()
        self.log_queue = log_queue
        self.setFormatter(logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        ))
        self._last_warning = None
        self._warning_count = 0

    def emit(self, record):
        try:
            msg_text = record.getMessage()
            if "pynvml" in msg_text:
                return
            msg = self.format(record)
            if record.levelno == logging.WARNING:
                if self._last_warning == msg:
                    self._warning_count += 1
                    return
                elif self._warning_count > 0:
                    merged = f"[合并 {self._warning_count} 条相同警告] {self._last_warning}"
                    self.log_queue.append(merged)
                    self._warning_count = 0
                self._last_warning = msg
            self.log_queue.append(msg)
        except Exception as e:
            logger.debug("QueueLogHandler emit failed: %s", e)

    def flush_warning_cache(self):
        if self._warning_count > 0 and self._last_warning:
            merged = f"[合并 {self._warning_count} 条相同警告] {self._last_warning}"
            self.log_queue.append(merged)
            self._warning_count = 0
            self._last_warning = None


class StreamToQueue:
    """将sys.stdout/stderr重定向到队列"""

    def __init__(self, log_queue: deque, stream=None):
        self.log_queue = log_queue
        self.original_stream = stream if stream else sys.stdout

    def write(self, text):
        if text and text.strip():
            try:
                self.log_queue.append(text.strip())
            except Exception as e:
                logger.debug("StreamToQueue append failed: %s", e)
        try:
            self.original_stream.write(text)
        except Exception as e:
            logger.debug("StreamToQueue write to original stream failed: %s", e)

    def flush(self):
        try:
            self.original_stream.flush()
        except Exception as e:
            logger.debug("StreamToQueue flush failed: %s", e)

    def isatty(self):
        try:
            return self.original_stream.isatty()
        except Exception:
            return False

    @property
    def encoding(self):
        try:
            return self.original_stream.encoding or "utf-8"
        except AttributeError:
            return "utf-8"

    @property
    def errors(self):
        try:
            return self.original_stream.errors or "replace"
        except AttributeError:
            return "replace"

    @property
    def mode(self):
        try:
            return self.original_stream.mode
        except AttributeError:
            return "w"


class LogService:
    """日志捕获与管理"""

    _INITIALIZED = False
    MAX_LOG_LINES = 1000

    def __init__(self):
        self.log_queue: deque = deque(maxlen=self.MAX_LOG_LINES)
        self.queue_handler: Optional[QueueLogHandler] = None
        self._setup_logging()

    def _setup_logging(self):
        root_logger = logging.getLogger()

        if LogService._INITIALIZED:
            for h in root_logger.handlers:
                if isinstance(h, QueueLogHandler):
                    h.log_queue = self.log_queue
                    self.queue_handler = h
                    return
            self.queue_handler = QueueLogHandler(self.log_queue)
            self.queue_handler.setLevel(logging.INFO)
            root_logger.addHandler(self.queue_handler)
            return

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        console_handler.setLevel(logging.INFO)
        root_logger.addHandler(console_handler)

        self.queue_handler = QueueLogHandler(self.log_queue)
        self.queue_handler.setLevel(logging.INFO)
        root_logger.addHandler(self.queue_handler)

        root_logger.setLevel(logging.INFO)
        logging.getLogger("torch").setLevel(logging.ERROR)
        logging.getLogger("ultralytics").setLevel(logging.WARNING)

        LogService._INITIALIZED = True

    def get_messages(self, max_lines: int = 100) -> str:
        messages = []
        # 取最近的日志（保留原队列供后续增量读取）
        for msg in list(self.log_queue)[-max_lines:]:
            if len(msg) > 500:
                msg = msg[:500] + " ... [截断]"
            messages.append(msg)
        return "\n".join(messages)
