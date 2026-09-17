"""兼容 shim：训练 worker 已迁移到 :mod:`src.worker`（2026-09-17）。

保留一个版本，供仍写死旧路径的脚本与文档使用：

    python -m src.gradio_app.worker <payload.json>   # 仍可用，请改用 src.worker

迁移原因：训练服务 / 队列是活跃功能，不该依赖已冻结的 ``gradio_app`` 层。
"""
from __future__ import annotations

from src.worker import _first_failure, _run, _write_status, main

__all__ = ["_first_failure", "_run", "_write_status", "main"]


if __name__ == "__main__":
    import sys

    sys.exit(main())
