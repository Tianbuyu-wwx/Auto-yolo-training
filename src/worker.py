"""
训练子进程 worker（阶段 P2：进程隔离）

调用方（TrainingService / QueueRunner）通过 ``python -m src.worker <payload.json>``
启动本模块，实现训练与 Web 进程隔离：主进程崩溃/重启不再杀死训练；训练崩溃不
影响 UI。

历史：2026-09-17 从 ``src.gradio_app.worker`` 迁出 —— 训练服务与任务队列都是
活跃功能，而 ``gradio_app`` 已冻结；活跃功能不该依赖冻结层（迁出后 gradio 才能
降级为可选依赖）。旧路径保留一个版本的 shim。

协议（文件握手，路径由 payload 指定）：
- payload.json   输入：TrainingConfig 字典 + base_dir
- <stem>.log     输出：训练全部 stdout/stderr（tee 到本文件）
- <stem>.stop    输入：主进程 touch 此文件 → 流水线在当前 epoch 结束后优雅停止
- <stem>.status  输出：{"phase": running|done, success, error_message, best_model_path, task}
"""

from __future__ import annotations

import contextlib
import json
import logging
import sys
import threading
import time
from pathlib import Path

logger = logging.getLogger("ayt.worker")


class _Tee:
    """同时写入原流和日志文件"""

    def __init__(self, original, file_obj):
        self.original = original
        self.file_obj = file_obj

    def write(self, text):
        with contextlib.suppress(Exception):
            self.original.write(text)
        try:
            self.file_obj.write(text)
            self.file_obj.flush()
        except Exception:
            pass

    def flush(self):
        with contextlib.suppress(Exception):
            self.original.flush()
        with contextlib.suppress(Exception):
            self.file_obj.flush()

    def isatty(self):
        return False

    @property
    def encoding(self):
        return getattr(self.original, "encoding", None) or "utf-8"

    @property
    def errors(self):
        return getattr(self.original, "errors", None) or "replace"

    @property
    def mode(self):
        return getattr(self.original, "mode", "w")


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python -m src.worker <payload.json>")
        return 2

    payload_path = Path(sys.argv[1])
    payload = json.loads(payload_path.read_text(encoding="utf-8"))

    base_dir = Path(payload["base_dir"])
    stem = payload_path.with_suffix("")
    log_path = stem.with_suffix(".log")
    status_path = stem.with_suffix(".status")
    stop_flag_path = stem.with_suffix(".stop")

    log_path.parent.mkdir(parents=True, exist_ok=True)

    # 子进程日志：tee 到文件（主进程监控页读取 tail）
    with open(log_path, "a", encoding="utf-8") as log_file:
        sys.stdout = _Tee(sys.stdout, log_file)
        sys.stderr = _Tee(sys.stderr, log_file)
        return _run(payload, base_dir, status_path, stop_flag_path)


def _write_status(status_path: Path, **fields) -> None:
    status_path.write_text(json.dumps(fields, ensure_ascii=False), encoding="utf-8")


def _run(payload: dict, base_dir: Path, status_path: Path, stop_flag_path: Path) -> int:
    from src.gradio_app.models.training_state import TrainingConfig

    config = TrainingConfig(**payload["config"])

    logging.basicConfig(level=logging.INFO, stream=sys.stdout, force=True)
    _write_status(status_path, phase="running", success=False, error_message="",
                  best_model_path="")

    from src.training_pipeline import TrainingPipeline

    pipeline = TrainingPipeline(base_dir=str(base_dir), max_backup_runs=2)

    def _should_stop() -> bool:
        return stop_flag_path.exists()

    started = time.time()
    logger.info("[WORKER] 训练子进程启动: dataset=%s model=%s epochs=%d",
                config.dataset_name, config.model, config.epochs)

    try:
        report = pipeline.run(
            dataset_name=config.dataset_name,
            model=config.model,
            imgsz=config.imgsz,
            batch=config.batch,
            epochs=config.epochs,
            skip_validation=config.skip_validation,
            training_overrides=config.to_overrides(),
            should_stop=_should_stop,
            enable_tuning=False,
            enable_evaluation=True,
            enable_export=False,
            auto_cleanup=True,
        )
    except Exception as e:  # 任何异常都要落到 status 文件，主进程才能展示
        logger.exception("[WORKER] 训练异常")
        _write_status(status_path, phase="done", success=False,
                      error_message=str(e), best_model_path="")
        return 1

    if _should_stop():
        _write_status(status_path, phase="done", success=False,
                      error_message="训练已被用户手动停止", best_model_path="")
        return 0

    best_model = ""
    for stage in report.stages:
        if stage["stage"] == "training" and stage["success"]:
            best_model = stage["details"].get("best_model") or ""
            break

    _write_status(
        status_path,
        phase="done",
        success=bool(report.success),
        error_message="" if report.success else _first_failure(report.stages),
        best_model_path=best_model,
        duration_seconds=round(time.time() - started, 2),
    )
    return 0 if report.success else 1


def _first_failure(stages: list) -> str:
    for stage in stages:
        if not stage.get("success"):
            return stage.get("message") or "训练失败"
    return "训练失败"


if __name__ == "__main__":
    threading.excepthook = lambda args: logger.critical(
        "Unhandled thread error", exc_info=args.exc_value
    )
    sys.exit(main())
