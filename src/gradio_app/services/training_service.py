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
from src.utils import recycle_path

logger = logging.getLogger(__name__)

# 优雅停止等待窗口：超过后强制 terminate 训练子进程（秒）
_STOP_GRACE_SECONDS = 60

# 项目根（src 的父目录）：保证 worker 子进程可 import src.*，
# 与 base_dir（数据目录，测试时可为临时目录）解耦
_PROJECT_ROOT = Path(__file__).resolve().parents[3]

# config_generator 生成的数据集 YAML 命名约定：data_<dataset>.yaml
_DATA_YAML_PREFIX = "data_"


def _read_flat_yaml(path: Path) -> dict[str, str]:
    """读取 Ultralytics 生成的扁平 args.yaml 的顶层标量。

    刻意不引入 yaml 依赖：该文件由 Ultralytics `yaml_save` 机械写出，全部是
    `key: value` 单行标量，没有嵌套、多行标量与锚点。按**首个**冒号切分，
    因此 Windows 路径里的盘符冒号（`E:\\项目\\…`）不会干扰取值。
    """
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        # 跳过缩进行（嵌套/列表）、注释与空行
        if not line or line[0] in " \t#-":
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        out[key.strip()] = value.strip()
    return out


def _dataset_from_args(args: dict[str, str]) -> str:
    """由 args.yaml 的 data 字段反推数据集名（约定 data_<dataset>.yaml）。

    刻意不用 `Path(...).stem`：args.yaml 由 Ultralytics 在**训练所在平台**写出，
    Windows 上是 `E:\\ds\\…\\data_my-ds.yaml`，而反斜杠在 POSIX 上不是路径分隔符，
    `Path().stem` 会返回整串路径。这里按两种分隔符手工取末段，跨平台一致。
    """
    raw = (args.get("data") or "").strip().strip("\"'")
    if not raw:
        return ""
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    if name.lower().endswith((".yaml", ".yml")):
        name = name.rsplit(".", 1)[0]
    if name.startswith(_DATA_YAML_PREFIX):
        return name[len(_DATA_YAML_PREFIX):]
    return name


def _count_epochs_done(results_csv: Path) -> int:
    """results.csv 行数（去表头）= 已完成轮数。

    训练进行中该文件可能停在半行上，因此只统计字段数与表头一致的行，
    否则会把写了一半的当前 epoch 记成"已完成"。
    """
    try:
        with results_csv.open(encoding="utf-8", errors="replace") as f:
            header = f.readline()
            if not header.strip():
                return 0
            expected = header.count(",") + 1
            return sum(1 for line in f if line.count(",") + 1 == expected)
    except OSError:
        return 0


class TrainingService:
    """训练任务管理"""

    # worker 日志 tail 的反向读取块大小
    LOG_TAIL_CHUNK = 64 * 1024

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
        # worker 日志 tail 缓存：文件未变化时（mtime/size/max_lines 相同）直接复用
        self._log_tail_cache_key: tuple | None = None
        self._log_tail_cache: str = ""

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
        """读取 worker 日志的最后 max_lines 行

        原实现是 ``f.readlines()[-max_lines:]`` —— 先把整个文件读进内存再丢掉
        99%。本方法每秒被调用一次（WebSocket 推送 + 状态轮询），长任务日志可
        达数 MB，等于每秒一次全量磁盘读 + 分配。

        改为从文件末尾反向按块读取，凑满 max_lines 个换行即停；并缓存
        (mtime_ns, size, max_lines) 作为键，文件未变化时直接复用上一次结果
        （训练空闲时几乎零开销）。

        Note:
            反向读取会在 buf 头部留下一个可能被截断的多字节 UTF-8 字符。因为
            只在 ``换行数 > max_lines`` 时才提前停止，这个残缺的首"行"必然
            落在被丢弃的前缀里，不会进入返回值。
        """
        log_path = self.worker_payload_path.with_suffix(".log") if self.worker_payload_path else None
        if not log_path or not log_path.exists():
            return ""
        try:
            stat = log_path.stat()
            cache_key = (stat.st_mtime_ns, stat.st_size, max_lines)
            if cache_key == self._log_tail_cache_key:
                return self._log_tail_cache

            with open(log_path, "rb") as f:
                pos = stat.st_size
                buf = b""
                while pos > 0 and buf.count(b"\n") <= max_lines:
                    step = min(self.LOG_TAIL_CHUNK, pos)
                    pos -= step
                    f.seek(pos)
                    buf = f.read(step) + buf

            text = buf.decode("utf-8", errors="replace")
            # 按「带换行符的行」切分，语义对齐 readlines()。
            # 注意不能直接 text.split("\n") 后取 [-max_lines:] —— 文本以 \n 结尾时
            # split 会多出一个空尾元素，它会吃掉一个名额，于是 100 行只返回 99 行、
            # max_lines=1 时直接返回空串。
            if text.endswith("\n"):
                parts = text[:-1].split("\n")
                lines = [p + "\n" for p in parts]
            else:
                parts = text.split("\n")
                lines = [p + "\n" for p in parts[:-1]] + [parts[-1]]
            if len(lines) > max_lines:
                lines = lines[-max_lines:]
            result = "".join(lines)

            self._log_tail_cache_key = cache_key
            self._log_tail_cache = result
            return result
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

    def list_checkpoint_details(self) -> list[dict[str, Any]]:
        """可续训断点的详细信息，按最近修改倒序。

        只给路径是不够的：续训**必须用回原数据集**——管线在 resume 模式下仍会把
        当前 config 的 `dataset_name` 显式传给 `model.train(data=…)`，选错数据集
        不会报错，只会在别的数据上接着练，产出无意义。因此这里把 args.yaml 的
        `data`（→ 数据集名）、`epochs`（计划轮数）与 results.csv 行数（已完成轮数）
        一并取出，让界面能按数据集约束断点选择。
        """
        details: list[dict[str, Any]] = []
        for raw in self.list_checkpoints():
            last_pt = Path(raw)
            run_dir = last_pt.parent.parent
            try:
                stat = last_pt.stat()
            except OSError:
                continue
            args = _read_flat_yaml(run_dir / "args.yaml")
            try:
                planned = int(float(args.get("epochs", "") or 0))
            except ValueError:
                planned = 0
            details.append({
                "path": str(last_pt),
                "run": run_dir.name,
                "dataset": _dataset_from_args(args),
                "epochs_done": _count_epochs_done(run_dir / "results.csv"),
                "epochs_planned": planned,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "mtime": stat.st_mtime,
            })
        details.sort(key=lambda d: d["mtime"], reverse=True)
        for d in details:
            del d["mtime"]   # 仅用于排序，不对外暴露
        return details

    def compare_runs_markdown(self, run_names: list[str] | None = None) -> str:
        """横向对比多个 run 的最终指标（P3-3 训练对比，直接读 results.csv）"""
        if not run_names:
            run_names = self.list_runs()[:10]

        lines = [
            "| Run | Epoch | 主要指标 |",
            "|-----|-------|----------|",
        ]
        found = False
        for run_name in run_names:
            results = self.get_training_results(run_name)
            metrics = results.get("final_metrics") if "error" not in results else None
            if not metrics:
                continue
            found = True
            primary = metrics.get("primary", {})
            parts = [f"{lb}: {v:.4f}" for lb, v in primary.items()] or ["无指标"]
            lines.append(f"| `{run_name}` | {metrics.get('epoch', '--')} | {'，'.join(parts)} |")

        if not found:
            return "暂无可对比的训练 run"

        lines.append("")
        lines.append("按 `list_runs` 顺序（新 → 旧）；完整版本管理见 ModelRegistry。")
        return "\n".join(lines)

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

    # 旧报告的归宿：runs/.recycle/_reports/（与 dataset/.recycle 同思路）
    RECYCLE_DIR_NAME = ".recycle"

    @property
    def runs_recycle_dir(self) -> Path:
        return self.paths.base_dir / "runs" / self.RECYCLE_DIR_NAME

    def _recycle_stale_reports(self, dataset_name: str) -> list[Path]:
        """把本数据集的旧报告移入回收站；最新一份留在原位。

        报告名由 pipeline / evaluator 机械生成：``pipeline_<dataset>_<时间戳>.json``
        与 ``<dataset>_best_eval_<时间戳>.json``。用**前缀精确匹配**，而不是
        ``dataset_name in 文件名`` —— 后者会把名字里含同一子串的别的数据集的报告
        一起删掉（``data``、``_smoke_test`` 这类短名字尤其容易撞）。
        """
        if not self.reports_dir.exists():
            return []
        prefixes = (f"pipeline_{dataset_name}_", f"{dataset_name}_best_eval_")
        matches = [
            p for p in self.reports_dir.iterdir()
            if p.is_file() and p.name.startswith(prefixes)
        ]
        if len(matches) < 2:
            return []
        matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        recycle_root = self.runs_recycle_dir / "_reports"
        recycled: list[Path] = []
        for path in matches[1:]:
            dest = recycle_path(path, recycle_root)
            if dest is not None:
                recycled.append(dest)
        return recycled

    def _export_best_model_and_cleanup(self, dataset_name: str):
        """导出最佳模型到 exports/，并把本数据集的旧报告移入回收站。

        2026-09-17 修复三处不可恢复的数据丢失（旧实现）：

        1. 删除判据是子串匹配（``dataset_name in item.name``）—— 实测
           ``dataset="mine"`` 会连带删掉 ``my-mine-other_auto``（另一个数据集的
           全部训练产物：权重、results.csv、全部曲线图）；
        2. ``shutil.move(best.pt → exports/)`` 把权重从 run 里搬走，同时
           ``rmtree`` 掉整个 run 目录 —— ``last.pt`` 随之消失，该 run 不再可续训，
           结果页 / 下载 / 按 run 注册随之全部失效；
        3. 同一次调用还会删掉本次训练刚写出的 pipeline 报告。

        现在的语义：**只导出、只回收报告，不碰 run 目录**。
        - ``copy2`` 导出到 ``exports/<dataset>.pt``，run 原位保留（仍是活的 run）；
        - 旧报告移入 ``runs/.recycle/_reports/``，最新一份留在原位；
        - run 的滚动保留统一由 ``TrainingPipeline._cleanup_old_runs`` 负责
          （精确正则 + 只留 max_backup_runs 个，同样是回收而非抹掉）。本方法
          不再自带一套保留策略 —— 两套口径互相打架正是这次事故的成因。
        """
        self.exports_dir.mkdir(parents=True, exist_ok=True)

        best_model_path = Path(self.state.best_model_path)
        if not best_model_path.exists():
            logger.warning("[EXPORT] 最佳模型不存在: %s", best_model_path)
            return

        target_name = f"{dataset_name}.pt"
        target_path = self.exports_dir / target_name

        try:
            if target_path.exists():
                logger.info("[EXPORT] 已覆盖已有模型: %s", target_name)
            # copy2 而不是 move：run 目录保持完整，断点续训与结果页都还指着它
            shutil.copy2(best_model_path, target_path)
            logger.info("[EXPORT] 最佳模型已导出: %s（run 原位保留: %s）",
                        target_path, best_model_path)
            self.state.update(best_model_path=str(target_path))

            recycled_reports = self._recycle_stale_reports(dataset_name)
            if recycled_reports:
                logger.info("[CLEANUP] %d 份旧报告已移入回收站: %s",
                            len(recycled_reports), self.runs_recycle_dir / "_reports")

        except Exception as e:
            logger.error("[EXPORT] 模型导出与回收失败: %s", e)

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
