"""
训练任务管理服务
"""

import sys
import shutil
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

from src.gradio_app.models.training_state import TrainingState, TrainingConfig
from src.gradio_app.services.log_service import LogService, StreamToQueue
from src.constants import ProjectPaths

logger = logging.getLogger(__name__)


class TrainingService:
    """训练任务管理"""

    def __init__(self, base_dir: Path, log_service: LogService):
        self.base_dir = base_dir
        self.paths = ProjectPaths(base_dir)
        self.runs_dir = self.paths.runs_dir
        self.exports_dir = self.paths.exports_dir
        self.reports_dir = self.paths.reports_dir
        self.log_service = log_service

        self.state = TrainingState()
        self.stop_event = threading.Event()
        self.training_thread: Optional[threading.Thread] = None

    def start(self, config: TrainingConfig) -> bool:
        """启动训练"""
        if self.state.is_running:
            return False

        self.state = TrainingState()
        self.state.update(
            is_running=True,
            start_time=datetime.now().isoformat(),
            total_epochs=config.epochs,
        )
        self.stop_event.clear()

        self.training_thread = threading.Thread(
            target=self._worker,
            args=(config,),
            daemon=True,
        )
        self.training_thread.start()
        return True

    def stop(self) -> bool:
        """停止训练"""
        if not self.state.is_running:
            return False
        self.state.update(is_stopping=True)
        self.stop_event.set()
        return True

    def get_status(self) -> Dict[str, Any]:
        """获取训练状态"""
        self._update_from_results()
        status = self.state.to_dict()
        status["logs"] = self.log_service.get_messages()
        return status

    def get_available_models(self) -> List[Dict[str, Any]]:
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

    def get_training_results(self, run_name: Optional[str] = None) -> Dict[str, Any]:
        """获取训练结果"""
        if run_name:
            run_dir = self.runs_dir / run_name
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

        # 读取最终指标
        csv_path = run_dir / "results.csv"
        if csv_path.exists():
            try:
                import pandas as pd
                df = pd.read_csv(csv_path)
                if not df.empty:
                    last_row = df.iloc[-1]
                    results["final_metrics"] = {
                        "epoch": int(last_row.get("epoch", 0)),
                        "mAP50": round(float(last_row.get("metrics/mAP50(B)", 0)), 4),
                        "mAP50_95": round(float(last_row.get("metrics/mAP50-95(B)", 0)), 4),
                    }
            except Exception as e:
                logger.debug("[RESULTS] 读取训练指标失败: %s", e)

        return results

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

            # 查找最佳模型路径和指标
            for stage in report.stages:
                if stage["stage"] == "training" and stage["success"]:
                    self.state.update(
                        best_model_path=stage["details"].get("best_model"),
                    )
                    metrics = stage["details"].get("metrics", {})
                    self.state.update(
                        current_map50=metrics.get("metrics/mAP50(B)", 0.0),
                        current_map50_95=metrics.get("metrics/mAP50-95(B)", 0.0),
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
            self.state.update(is_running=False, is_stopping=False)
            if self.log_service.queue_handler:
                self.log_service.queue_handler.flush_warning_cache()

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

            with open(csv_path, "r", encoding="utf-8") as f:
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
                    last_row = dict(zip(headers, values))
                    if "epoch" in last_row:
                        epoch = int(float(last_row["epoch"])) + 1
                        if epoch > self.state.current_epoch:
                            current_loss = float(last_row.get("train/box_loss", 0))
                            current_map50 = float(last_row.get("metrics/mAP50(B)", 0))
                            current_map50_95 = float(last_row.get("metrics/mAP50-95(B)", 0))
                            self.state.update(
                                current_epoch=min(epoch, self.state.total_epochs),
                                current_map50=current_map50,
                                current_map50_95=current_map50_95,
                                current_loss=current_loss,
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
