"""
SQLite 任务队列（阶段 F 前置：训练任务排队 / 持久化 / 崩溃恢复）

设计：
- 队列表 tasks 持久化到 SQLite（默认 logs/task_queue.db），Web 重启不丢任务
- 任务执行复用 gradio_app.worker 子进程（进程隔离 + 日志文件 + 停止握手）
- QueueRunner 在后台线程排队执行（默认串行，GPU 任务并发=1）
- 取消：queued → 直接 cancelled；running → 写 stop 标志，worker 优雅停止

CLI（独立消费队列）:
    python -m src.task_queue            # 处理队列直到 Ctrl+C
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 任务状态机：queued → running → done / failed / cancelled
TASK_QUEUED = "queued"
TASK_RUNNING = "running"
TASK_DONE = "done"
TASK_FAILED = "failed"
TASK_CANCELLED = "cancelled"


class TaskQueue:
    """基于 SQLite 的训练任务队列（单进程内多线程安全）"""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset_name TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    error TEXT DEFAULT '',
                    best_model_path TEXT DEFAULT ''
                )
                """
            )

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        out = dict(row)
        out["config"] = json.loads(out.pop("config_json"))
        return out

    # ------------------------------------------------------------------
    # 写操作
    # ------------------------------------------------------------------
    def enqueue(self, dataset_name: str, config: dict[str, Any]) -> int:
        """入队一个训练任务，返回任务 id"""
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO tasks (dataset_name, config_json, status, created_at)"
                " VALUES (?, ?, ?, ?)",
                (dataset_name, json.dumps(config, ensure_ascii=False),
                 TASK_QUEUED, datetime.now().isoformat()),
            )
            return int(cur.lastrowid)

    def claim_next(self) -> dict[str, Any] | None:
        """原子领取下一个 queued 任务（status → running）"""
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY id LIMIT 1",
                (TASK_QUEUED,),
            ).fetchone()
            if row is None:
                return None
            self._conn.execute(
                "UPDATE tasks SET status = ?, started_at = ? WHERE id = ?",
                (TASK_RUNNING, datetime.now().isoformat(), row["id"]),
            )
            claimed = self._row_to_dict(row)
            claimed["status"] = TASK_RUNNING
            return claimed

    def mark_finished(self, task_id: int, success: bool, error: str = "",
                      best_model_path: str = "") -> None:
        status = TASK_DONE if success else TASK_FAILED
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE tasks SET status = ?, finished_at = ?, error = ?, best_model_path = ?"
                " WHERE id = ?",
                (status, datetime.now().isoformat(), error, best_model_path, task_id),
            )

    def cancel(self, task_id: int) -> bool:
        """取消任务：queued 直接取消；running 置 cancel_requested（由 runner 握手停止）"""
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT status FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            if row is None:
                return False
            if row["status"] == TASK_QUEUED:
                self._conn.execute(
                    "UPDATE tasks SET status = ?, finished_at = ? WHERE id = ?",
                    (TASK_CANCELLED, datetime.now().isoformat(), task_id),
                )
                return True
            if row["status"] == TASK_RUNNING:
                self._conn.execute(
                    "UPDATE tasks SET status = ? WHERE id = ?",
                    ("cancel_requested", task_id),
                )
                return True
            return False

    # ------------------------------------------------------------------
    # 读操作
    # ------------------------------------------------------------------
    def get_task(self, task_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            return self._row_to_dict(row) if row else None

    def list_tasks(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM tasks ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def is_cancel_requested(self, task_id: int) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT status FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            return bool(row) and row["status"] == "cancel_requested"


class QueueRunner:
    """后台线程消费任务队列；每个任务用 worker 子进程执行（进程隔离）"""

    def __init__(self, queue: TaskQueue, base_dir: str | Path,
                 poll_interval: float = 1.0):
        self.queue = queue
        self.base_dir = Path(base_dir)
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.current_task_id: int | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="queue-runner")
        self._thread.start()
        logger.info("[QUEUE] QueueRunner 已启动")

    def stop(self) -> None:
        self._stop_event.set()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                task = self.queue.claim_next()
            except Exception:
                logger.exception("[QUEUE] 领取任务失败")
                task = None
            if task is None:
                time.sleep(self.poll_interval)
                continue
            self.current_task_id = task["id"]
            try:
                self._execute(task)
            except Exception:
                logger.exception("[QUEUE] 执行任务 %s 异常", task["id"])
                with contextlib.suppress(Exception):
                    self.queue.mark_finished(task["id"], success=False,
                                              error="runner 执行异常")
            finally:
                self.current_task_id = None

    def _execute(self, task: dict[str, Any]) -> None:
        """用 worker 子进程执行一个队列任务"""
        logs_dir = self.base_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        stem = logs_dir / f"queue_task_{task['id']:06d}"
        payload_path = stem.with_suffix(".json")
        payload_path.write_text(
            json.dumps({"base_dir": str(self.base_dir), "config": task["config"]},
                       ensure_ascii=False),
            encoding="utf-8",
        )
        stop_flag = stem.with_suffix(".stop")

        project_root = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(
            [str(project_root), str(self.base_dir), env.get("PYTHONPATH", "")]
        )

        logger.info("[QUEUE] 启动任务 %s (dataset=%s)", task["id"], task["dataset_name"])
        proc = subprocess.Popen(
            [sys.executable, "-m", "src.gradio_app.worker", str(payload_path)],
            cwd=str(project_root), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

        # 等待结束；期间响应取消请求（写 stop 标志 → worker 优雅停止）
        while proc.poll() is None:
            if self._stop_event.is_set():
                logger.warning("[QUEUE] runner 停止，强制终止任务 %s 子进程", task["id"])
                proc.terminate()
                self.queue.mark_finished(task["id"], success=False,
                                         error="队列服务停止，任务中断")
                return
            if self.queue.is_cancel_requested(task["id"]) and not stop_flag.exists():
                with contextlib.suppress(OSError):
                    stop_flag.touch()
            time.sleep(1.0)

        status = {}
        status_path = stem.with_suffix(".status")
        with contextlib.suppress(Exception):
            status = json.loads(status_path.read_text(encoding="utf-8"))

        success = bool(status.get("success"))
        self.queue.mark_finished(
            task["id"], success=success,
            error=status.get("error_message", "") if not success else "",
            best_model_path=status.get("best_model_path", ""),
        )
        # 清理握手文件，保留日志
        for p in (payload_path, status_path, stop_flag):
            with contextlib.suppress(OSError):
                p.unlink(missing_ok=True)
        logger.info("[QUEUE] 任务 %s 完成: %s", task["id"],
                    "done" if success else status.get("error_message", "failed"))


def main() -> int:
    """独立消费队列：python -m src.task_queue [db_path]"""
    db = sys.argv[1] if len(sys.argv) > 1 else "logs/task_queue.db"
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
    queue = TaskQueue(db)
    runner = QueueRunner(queue)
    runner.start()
    logger.info("[QUEUE] 队列服务已启动 (db=%s)，Ctrl+C 退出", db)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        runner.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
