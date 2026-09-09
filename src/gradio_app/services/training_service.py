"""
训练任务管理服务

P2 起支持进程隔离（默认）：训练在独立子进程（worker.py）执行，
Gradio 主进程重启不影响训练；日志经文件 tail 回传，停止经标志文件握手。
保留 in-process 线程模式（use_subprocess=False）供测试与调试。
"""

import contextlib
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from src.constants import ProjectPaths
from src.gradio_app.models.training_state import TrainingConfig, TrainingState
from src.gradio_app.services.log_service import LogService, StreamToQueue
from src.model_catalog import resolve_model_task
from src.task_metrics import (
    infer_task_from_csv_headers,
    primary_loss_from_row,
    primary_metric_labels,
    primary_metrics_from_row,
)

logger = logging.getLogger(__name__)

# 优雅停止等待窗口：超过后强制 terminate 训练子进程（秒）
_STOP_GRACE_SECONDS = 60

# 项目根（src 的父目录）：保证 worker 子进程可 import src.*，
# 与 base_dir（数据目录，测试时可为临时目录）解耦
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


class TrainingService:
    """训练任务管理"""

    def __init__(self, base_dir: Path, log_service: LogService, use_subprocess: bool = True):
        self.base_dir = base_dir
        self.paths = ProjectPaths(base_dir)
        self.runs_dir = self.paths.runs_dir
        self.exports_dir = self.paths.exports_dir
        self.reports_dir = self.paths.reports_dir
        self.log_service = log_service
        self.use_subprocess = use_subprocess

        self.state = TrainingState()
        self.stop_event = threading.Event()
        self.training_thread: threading.Thread | None = None
        self.training_proc: subprocess.Popen | None = None
        self.worker_payload_path: Path | None = None
        # 监控页渲染签名（用于空闲时跳过重量级刷新）
        self.last_rendered_signature: tuple | None = None

    # ------------------------------------------------------------------
    # 启动 / 停止
    # ------------------------------------------------------------------
    def start(self, config: TrainingConfig) -> bool:
        """启动训练"""
        if self.state.is_running:
            return False

        self.state = TrainingState()
        # 任务感知：按模型文件名推断任务，指标标签随任务变化（segment→(M)，classify→Accuracy）
        task = config.task if config.task and config.task != "detect" else resolve_model_task(config.model)
        self.state.update(
            is_running=True,
            start_time=datetime.now().isoformat(),
            total_epochs=config.epochs,
            task=task,
            metric_labels=primary_metric_labels(task),
        )
        self.stop_event.clear()

        if self.use_subprocess:
            self._start_subprocess(config)
        else:
            self.training_thread = threading.Thread(
                target=self._worker,
                args=(config,),
                daemon=True,
            )
            self.training_thread.start()
        return True

    def _start_subprocess(self, config: TrainingConfig) -> None:
        """以独立子进程启动训练（进程隔离）"""
        logs_dir = self.paths.logs_dir
        logs_dir.mkdir(parents=True, exist_ok=True)
        stem = logs_dir / f"ayt_worker_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        payload_path = stem.with_suffix(".json")
        payload = {"base_dir": str(self.base_dir), "config": asdict(config)}
        payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                encoding="utf-8")
        self.worker_payload_path = payload_path

        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(
            [str(_PROJECT_ROOT), str(self.base_dir), env.get("PYTHONPATH", "")]
        )

        try:
            self.training_proc = subprocess.Popen(
                [sys.executable, "-m", "src.gradio_app.worker", str(payload_path)],
                cwd=str(_PROJECT_ROOT),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            logger.exception("[WORKER] 子进程启动失败")
            self.state.update(
                is_running=False, success=False,
                error_message=f"训练子进程启动失败: {e}",
                end_time=datetime.now().isoformat(),
            )
            return

        logger.info("[WORKER] 子进程已启动 pid=%d payload=%s",
                    self.training_proc.pid, payload_path.name)
        self.training_thread = threading.Thread(
            target=self._wait_subprocess, args=(config,), daemon=True,
        )
        self.training_thread.start()

    def _wait_subprocess(self, config: TrainingConfig) -> None:
        """等待训练子进程结束并回填状态"""
        proc = self.training_proc
        try:
            proc.wait()
            status = self._read_worker_status()
            self.state.update(
                success=bool(status.get("success")),
                error_message=status.get("error_message") or None,
                best_model_path=status.get("best_model_path") or None,
            )

            # 恢复最佳模型指标（从 results.csv 读）
            if self.state.best_model_path:
                run_dir = Path(self.state.best_model_path).parent.parent
                self._apply_final_metrics(run_dir)

            if status.get("success") and self.state.best_model_path:
                self._export_best_model_and_cleanup(config.dataset_name)
        except Exception as e:
            logger.exception("[WORKER] 等待子进程异常")
            self.state.update(success=False, error_message=str(e))
        finally:
            self._finish_state()
            self._cleanup_worker_files()

    def _read_worker_status(self) -> dict[str, Any]:
        """读取 worker 的最终状态文件"""
        if not self.worker_payload_path:
            return {}
        status_path = self.worker_payload_path.with_suffix(".status")
        try:
            return json.loads(status_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.debug("[WORKER] 读取状态文件失败: %s", e)
            return {"success": False, "error_message": "训练子进程异常退出（无状态文件）"}

    def _cleanup_worker_files(self) -> None:
        """清理 worker 握手文件（保留日志供排查）"""
        if not self.worker_payload_path:
            return
        for suffix in (".json", ".status", ".stop"):
            with contextlib.suppress(OSError):
                self.worker_payload_path.with_suffix(suffix).unlink(missing_ok=True)

    def stop(self) -> bool:
        """停止训练"""
        if not self.state.is_running:
            return False
        self.state.update(is_stopping=True)

        if self.use_subprocess and self.training_proc and self.training_proc.poll() is None:
            # 握手：touch stop 标志 → worker 在当前 epoch 结束后优雅停止
            if self.worker_payload_path:
                with contextlib.suppress(OSError):
                    self.worker_payload_path.with_suffix(".stop").touch()
            # 超过等待窗口仍存活则强杀
            def _force_kill():
                time.sleep(_STOP_GRACE_SECONDS)
                if self.training_proc and self.training_proc.poll() is None:
                    logger.warning("[WORKER] 优雅停止超时，强制终止子进程")
                    self.training_proc.terminate()

            threading.Thread(target=_force_kill, daemon=True).start()
        else:
            self.stop_event.set()
        return True

    def _finish_state(self) -> None:
        self.state.update(is_running=False, is_stopping=False,
                          end_time=datetime.now().isoformat())
        if self.log_service.queue_handler:
            self.log_service.queue_handler.flush_warning_cache()

    # ------------------------------------------------------------------
    # 状态读取
    # ------------------------------------------------------------------
    def get_status(self) -> dict[str, Any]:
        """获取训练状态"""
        self._update_from_results()
        status = self.state.to_dict()
        status["logs"] = self._collect_logs()
        return status

    def _collect_logs(self) -> str:
        """训练日志：子进程模式读 worker 日志文件 tail；否则用进程内队列"""
        if self.use_subprocess and self.worker_payload_path:
            return self._read_worker_log_tail()
        return self.log_service.get_messages()

    def _read_worker_log_tail(self, max_lines: int = 100) -> str:
        log_path = self.worker_payload_path.with_suffix(".log") if self.worker_payload_path else None
        if not log_path or not log_path.exists():
            return ""
        try:
            with open(log_path, encoding="utf-8", errors="replace") as f:
                return "".join(f.readlines()[-max_lines:])
        except Exception as e:
            logger.debug("[WORKER] 读取日志失败: %s", e)
            return ""

    def get_available_models(self) -> list[dict[str, Any]]:
        """获取可用模型列表"""
        models = []
        if self.runs_dir.exists():
            for run_dir in sorted(self.runs_dir.iterdir(), key=lambda d: d.stat().st_mtime, reverse=True):
                weights_dir = run_dir / "weights"
                if weights_dir.exists():
                    for weight_file in weights_dir.glob("*.pt"):
                        stat = weight_file.stat()
                        models.append({
                            "name": weight_file.stem,
                            "path": str(weight_file),
                            "run": run_dir.name,
                            "size_mb": round(stat.st_size / (1024 * 1024), 2),
                            "created": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                        })
        return models

    def list_runs(self) -> list[str]:
        """列出含训练产物（results.csv 或 best.pt）的历史 run 目录名"""
        runs = []
        if self.runs_dir.exists():
            for run_dir in self.runs_dir.iterdir():
                if run_dir.is_dir() and (
                    (run_dir / "results.csv").exists() or (run_dir / "weights" / "best.pt").exists()
                ):
                    runs.append(run_dir.name)
        return sorted(runs, reverse=True)

    def list_checkpoints(self) -> list[str]:
        """列出可恢复训练的 last.pt（P2-4 断点续训）"""
        checkpoints = []
        if self.runs_dir.exists():
            for run_dir in self.runs_dir.iterdir():
                last_pt = run_dir / "weights" / "last.pt"
                if last_pt.exists():
                    checkpoints.append(str(last_pt))
        return sorted(checkpoints, reverse=True)

    def get_training_results(self, run_name: str | None = None) -> dict[str, Any]:
        """获取训练结果"""
        if run_name:
            run_dir = self.runs_dir / run_name
            if not run_dir.exists():
                return {"error": f"run 不存在: {run_name}"}
        else:
            if not self.runs_dir.exists():
                return {"error": "没有找到训练结果"}
            run_dirs = sorted(
                [d for d in self.runs_dir.iterdir() if d.is_dir()],
                key=lambda d: d.stat().st_mtime, reverse=True,
            )
            if not run_dirs:
                return {"error": "没有找到训练结果"}
            run_dir = run_dirs[0]

        results = {
            "run_name": run_dir.name,
            "run_path": str(run_dir),
            "has_weights": (run_dir / "weights" / "best.pt").exists(),
            "has_results": (run_dir / "results.csv").exists(),
        }

        # 收集结果图像
        result_images = []
        for img_name in ["confusion_matrix.png", "F1_curve.png", "P_curve.png",
                         "R_curve.png", "PR_curve.png", "results.png"]:
            img_path = run_dir / img_name
            if img_path.exists():
                result_images.append(str(img_path))
        results["result_images"] = result_images

        # 读取最终指标（任务感知：按 csv 列名推断任务）
        csv_path = run_dir / "results.csv"
        if csv_path.exists():
            try:
                import pandas as pd
                df = pd.read_csv(csv_path)
                df.columns = [c.strip() for c in df.columns]
                if not df.empty:
                    last_row = df.iloc[-1]
                    task = infer_task_from_csv_headers(list(df.columns))
                    row = {str(k): str(v) for k, v in last_row.items()}
                    primary = primary_metrics_from_row(row, task)
                    labels = list(primary.keys())
                    results["task"] = task.value if hasattr(task, "value") else str(task)
                    results["metric_labels"] = primary_metric_labels(task)
                    results["final_metrics"] = {
                        "epoch": int(float(last_row.get("epoch", 0))),
                        "mAP50": round(primary.get(labels[0], 0.0), 4) if labels else 0.0,
                        "mAP50_95": round(primary.get(labels[1], 0.0), 4) if len(labels) > 1 else 0.0,
                        "primary": {k: round(v, 4) for k, v in primary.items()},
                    }
            except Exception as e:
                logger.debug("[RESULTS] 读取训练指标失败: %s", e)

        return results

    # ------------------------------------------------------------------
    # In-process 训练线程（测试/调试模式）
    # ------------------------------------------------------------------
    def _worker(self, config: TrainingConfig):
        """训练工作线程"""
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = StreamToQueue(self.log_service.log_queue, stream=old_stdout)
        sys.stderr = StreamToQueue(self.log_service.log_queue, stream=old_stderr)

        try:
            from src.training_pipeline import TrainingPipeline

            def progress_callback(stage: str, progress: float):
                self.state.update(current_stage=stage)
                if stage == "training":
                    self.state.update(current_epoch=int(progress * config.epochs))

            pipeline = TrainingPipeline(base_dir=str(self.base_dir), max_backup_runs=2)

            report = pipeline.run(
                dataset_name=config.dataset_name,
                model=config.model,
                imgsz=config.imgsz,
                batch=config.batch,
                epochs=config.epochs,
                skip_validation=config.skip_validation,
                training_overrides=config.to_overrides(),
                progress_callback=progress_callback,
                should_stop=self.stop_event.is_set,
                enable_tuning=False,
                enable_evaluation=True,
                enable_export=False,
                auto_cleanup=True,
            )

            # 区分正常完成与手动停止
            if self.stop_event.is_set():
                self.state.update(
                    success=False,
                    end_time=datetime.now().isoformat(),
                    error_message="训练已被用户手动停止",
                )
            else:
                if report.success:
                    self.state.update(
                        success=True,
                        end_time=datetime.now().isoformat(),
                    )
                else:
                    # 从失败阶段提取错误信息
                    error_msg = "训练失败"
                    for stage in report.stages:
                        if not stage.get("success"):
                            error_msg = stage.get("message") or error_msg
                            break
                    self.state.update(
                        success=False,
                        end_time=datetime.now().isoformat(),
                        error_message=error_msg,
                    )

            # 查找最佳模型路径和指标（任务感知解析）
            for stage in report.stages:
                if stage["stage"] == "training" and stage["success"]:
                    self.state.update(
                        best_model_path=stage["details"].get("best_model"),
                    )
                    metrics = stage["details"].get("metrics", {})
                    primary = primary_metrics_from_row(
                        {k: str(v) for k, v in metrics.items()}, self.state.task
                    )
                    labels = list(primary.keys())
                    self.state.update(
                        current_map50=primary.get(labels[0], 0.0) if labels else 0.0,
                        current_map50_95=primary.get(labels[1], 0.0) if len(labels) > 1 else 0.0,
                    )
                    break

            # 导出最佳模型并清理
            if report.success and self.state.best_model_path:
                self._export_best_model_and_cleanup(config.dataset_name)

        except Exception as e:
            self.state.update(
                error_message=str(e),
                success=False,
                end_time=datetime.now().isoformat(),
            )
            logging.error(f"训练失败: {e}", exc_info=True)

        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            self._finish_state()

    def _apply_final_metrics(self, run_dir: Path) -> None:
        """从 run 目录 results.csv 回填最终指标（子进程模式）"""
        csv_path = run_dir / "results.csv"
        if not csv_path.exists():
            return
        try:
            with open(csv_path, encoding="utf-8") as f:
                header = f.readline().strip()
                lines = [ln for ln in f.read().strip().splitlines() if ln.strip()]
            if not header or not lines:
                return
            headers = header.split(",")
            values = lines[-1].split(",")
            if len(values) != len(headers):
                return
            row = dict(zip(headers, values, strict=True))
            primary = primary_metrics_from_row(row, self.state.task)
            labels = list(primary.keys())
            self.state.update(
                current_epoch=min(int(float(row.get("epoch", 0))) + 1, self.state.total_epochs),
                current_map50=primary.get(labels[0], 0.0) if labels else 0.0,
                current_map50_95=primary.get(labels[1], 0.0) if len(labels) > 1 else 0.0,
                current_loss=primary_loss_from_row(row),
            )
        except Exception as e:
            logger.debug("[RESULTS] 回填最终指标失败: %s", e)

    def _export_best_model_and_cleanup(self, dataset_name: str):
        """导出最佳模型并清理临时文件"""
        self.exports_dir.mkdir(parents=True, exist_ok=True)

        best_model_path = Path(self.state.best_model_path)
        if not best_model_path.exists():
            logger.warning("[EXPORT] 最佳模型不存在: %s", best_model_path)
            return

        target_name = f"{dataset_name}.pt"
        target_path = self.exports_dir / target_name

        try:
            if target_path.exists():
                target_path.unlink()
                logger.info("[EXPORT] 已覆盖已有模型: %s", target_name)

            shutil.move(str(best_model_path), str(target_path))
            logger.info("[EXPORT] 最佳模型已导出: %s", target_path)
            self.state.update(best_model_path=str(target_path))

            # 清理 runs 目录
            for runs_sub in ["detect", "train"]:
                runs_dir = self.paths.base_dir / "runs" / runs_sub
                if runs_dir.exists():
                    for item in runs_dir.iterdir():
                        if item.is_dir() and dataset_name in item.name:
                            try:
                                shutil.rmtree(item)
                                logger.info("[CLEANUP] 已删除: %s", item.name)
                            except Exception as e:
                                logger.warning("[CLEANUP] 删除失败 %s: %s", item.name, e)

            # 清理 reports
            if self.reports_dir.exists():
                for item in self.reports_dir.iterdir():
                    if item.is_file() and dataset_name in item.name:
                        try:
                            item.unlink()
                        except Exception as e:
                            logger.warning("[CLEANUP] 删除报告失败 %s: %s", item.name, e)

        except Exception as e:
            logger.error("[EXPORT] 模型导出与清理失败: %s", e)

    def _update_from_results(self):
        """从results.csv增量读取最新进度"""
        if not self.state.is_running:
            return

        try:
            if not self.runs_dir.exists():
                return
            run_dirs = sorted(
                [d for d in self.runs_dir.iterdir() if d.is_dir()],
                key=lambda d: d.stat().st_mtime, reverse=True,
            )
            if not run_dirs:
                return
            latest_run = run_dirs[0]
            csv_path = latest_run / "results.csv"

            if not csv_path.exists():
                return

            with open(csv_path, encoding="utf-8") as f:
                header = f.readline()
                if not header:
                    return
                f.seek(0, 2)
                file_size = f.tell()
                read_size = min(4096, file_size)
                f.seek(file_size - read_size)
                tail_content = f.read()

            lines = tail_content.strip().split('\n')
            last_line = lines[-1] if lines else None
            if last_line:
                headers = header.strip().split(',')
                values = last_line.strip().split(',')
                if len(values) == len(headers):
                    last_row = dict(zip(headers, values, strict=True))
                    if "epoch" in last_row:
                        epoch = int(float(last_row["epoch"])) + 1
                        if epoch > self.state.current_epoch:
                            current_map50 = current_map50_95 = 0.0
                            primary = primary_metrics_from_row(last_row, self.state.task)
                            labels = list(primary.keys())
                            if labels:
                                current_map50 = primary.get(labels[0], 0.0)
                                current_map50_95 = primary.get(labels[1], 0.0) if len(labels) > 1 else 0.0
                            current_loss = primary_loss_from_row(last_row)
                            now = time.time()
                            self.state.update(
                                current_epoch=min(epoch, self.state.total_epochs),
                                current_map50=current_map50,
                                current_map50_95=current_map50_95,
                                current_loss=current_loss,
                                eta_seconds=self._estimate_eta(now),
                            )
                            # 阶段 A14：追加曲线历史（设计变更，原 loss_history/map_history
                            # 字段定义了但 worker 从不写入，导致 Gradio LinePlot 永远空）
                            with self.state._lock:
                                # 避免重复追加同一 epoch
                                if not self.state.loss_history or \
                                        self.state.loss_history[-1]["epoch"] != epoch:
                                    self.state.loss_history.append({
                                        "epoch": epoch,
                                        "loss": current_loss,
                                    })
                                    self.state.map_history.append({
                                        "epoch": epoch,
                                        "mAP": current_map50,
                                    })
                                    # 历史上限保护：保留最近 1000 个 epoch 防止内存膨胀
                                    if len(self.state.loss_history) > 1000:
                                        self.state.loss_history = self.state.loss_history[-1000:]
                                        self.state.map_history = self.state.map_history[-1000:]

        except Exception as e:
            logger.debug("[PROGRESS] 增量读取训练进度失败: %s", e)

    def _estimate_eta(self, now: float) -> float | None:
        """按最近 epoch 完成节奏估算剩余时间（秒）。

        依据 state.epoch_timestamps 中最近若干个 epoch 间隔的平均值；
        样本不足（<2）或已到最后一个 epoch 时返回 None。
        """
        remaining = self.state.total_epochs - self.state.current_epoch
        if remaining <= 0:
            return 0.0
        stamps = self.state.epoch_timestamps
        if stamps and now - stamps[-1] > 3600 * 6:
            # 上次记录过久（如训练已中断重启），历史节奏不可信
            stamps.clear()
        stamps.append(now)
        if len(stamps) > 20:
            del stamps[:-20]
        if len(stamps) < 2:
            return None
        deltas = [b - a for a, b in zip(stamps, stamps[1:], strict=False)]
        avg = sum(deltas) / len(deltas)
        return round(avg * remaining, 1)
