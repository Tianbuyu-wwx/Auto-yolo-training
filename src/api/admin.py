"""
管理面 API（前端升级 M1）

把 DatasetService / TrainingService / TaskQueue 包成 REST + WebSocket，
供独立前端（frontend/，Vue 3 SPA）使用；Gradio 版与之并行，共用同一服务层。

挂载方式：
    from src.api.admin import create_admin_app
    app = create_admin_app(base_dir)   # 独立运行 (ayt-web)
    # 或挂到已有 FastAPI: app.mount("/admin", create_admin_app(...))

约定：
- REST 前缀 /api
- WebSocket /ws/training：每秒推送 {"status": ..., "logs": ...}
- frontend/dist 存在时自动静态托管（SPA 模式）
"""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.constants import ProjectPaths
from src.gradio_app.models.training_state import TrainingConfig
from src.gradio_app.services.dataset_service import DatasetService
from src.gradio_app.services.log_service import LogService
from src.gradio_app.services.training_service import TrainingService
from src.task_queue import QueueRunner, TaskQueue
from src.utils import is_path_allowed

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


# ----------------------------------------------------------------------
# Pydantic 请求模型
# ----------------------------------------------------------------------
def _build_models():
    """延迟构建 pydantic 模型（保持与 TrainingConfig 字段同步）"""
    from pydantic import BaseModel

    class StartTrainingRequest(BaseModel):
        """启动训练请求：字段与 TrainingConfig 对齐，经 from_ui 做类型归一"""

        dataset_name: str
        model: str = "yolov8s.pt"
        task: str = "detect"
        epochs: int = 150
        imgsz: int = 640
        batch: Any = 16  # 支持 -1 (AutoBatch)
        device: str = ""
        workers: int = 8
        lr0: float = 0.001
        optimizer: str = "AdamW"
        cos_lr: bool = True
        lrf: float = 0.01
        warmup_epochs: float = 3.0
        patience: int = 30
        dropout: float = 0.0
        mosaic: float = 1.0
        mixup: float = 0.0
        degrees: float = 0.0
        scale: float = 0.5
        translate: float = 0.1
        shear: float = 0.0
        perspective: float = 0.0
        flipud: float = 0.0
        hsv_h: float = 0.015
        hsv_s: float = 0.7
        hsv_v: float = 0.4
        cache: Any = "disk"
        rect: bool = True
        deterministic: bool = False
        freeze: int = 0
        label_smoothing: float = 0.0
        weight_decay: float = 0.0005
        box: float = 7.5
        cls: float = 0.5
        dfl: float = 1.5
        copy_paste: float = 0.0
        close_mosaic: int = 10
        skip_validation: bool = False
        resume_from: str = ""
        # True 时清单内缺失模型会同步下载（可能较慢）；False 时直接 400 提示先下载
        download_missing: bool = False

    class EnqueueRequest(StartTrainingRequest):
        """入队请求（同 Start 字段）"""

    class ExportRequest(BaseModel):
        run_name: str
        fmt: str = "onnx"

    class RegisterModelRequest(BaseModel):
        """注册模型版本请求。

        权重来源二选一：`run_name`（推荐，从 runs/ 派生，路径不可能越界）
        或 `model_path`（限 runs/ 、basemodels/ 、exports/ 白名单内）。
        `metrics` 留空时自动从该 run 的 results.csv 取最终指标 —— 让用户手抄 mAP
        既麻烦又容易抄错。
        """

        dataset_name: str
        run_name: str = ""
        weights: str = "best"  # best | last
        model_path: str = ""
        description: str = ""
        tags: list[str] = []
        metrics: dict[str, float] | None = None
        # 默认不复制：与训练管线的自动注册保持一致，避免把几百 MB 权重再存一份。
        # 复制的好处是 runs/ 被清理后注册表仍可用，所以交给用户决定。
        copy_model: bool = False

    class VersionStatusRequest(BaseModel):
        status: str

    class VersionTagsRequest(BaseModel):
        tags: list[str]

    return (
        StartTrainingRequest,
        EnqueueRequest,
        ExportRequest,
        RegisterModelRequest,
        VersionStatusRequest,
        VersionTagsRequest,
    )


(
    StartTrainingRequest,
    EnqueueRequest,
    ExportRequest,
    RegisterModelRequest,
    VersionStatusRequest,
    VersionTagsRequest,
) = _build_models()


class SPAStaticFiles(StaticFiles):
    """SPA 静态托管：前端路由路径（/queue 等）回退到 index.html。

    保持 404 的两类路径：
    - api/ 前缀：接口不存在应显式 404，不返回 HTML 掩盖错误
    - 带扩展名的路径：缺失的静态资源（如 /assets/xx.js）应 404
    """

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as e:
            last_segment = path.rsplit("/", 1)[-1]
            is_spa_route = (
                e.status_code == 404
                and not path.startswith(("api/", "ws/"))
                and "." not in last_segment
            )
            if is_spa_route:
                return await super().get_response("index.html", scope)
            raise


# ----------------------------------------------------------------------
# 应用工厂
# ----------------------------------------------------------------------
def create_admin_app(
    base_dir: str | Path | None = None,
    use_subprocess: bool = True,
    start_queue_runner: bool = True,
    frontend_dist: str | Path | None = None,
) -> FastAPI:
    """创建管理面 FastAPI 应用（服务层全部注入，测试时可替换）"""
    base = Path(base_dir).resolve() if base_dir else PROJECT_ROOT
    paths = ProjectPaths(base)

    log_svc = LogService()
    dataset_svc = DatasetService(base)
    training_svc = TrainingService(base, log_svc, use_subprocess=use_subprocess)
    task_queue = TaskQueue(paths.logs_dir / "task_queue.db")
    queue_runner = QueueRunner(task_queue, base)
    if start_queue_runner:
        queue_runner.start()

    app = FastAPI(title="AYT Admin API", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.base_dir = base
    app.state.services = {
        "dataset": dataset_svc,
        "training": training_svc,
        "queue": task_queue,
        "queue_runner": queue_runner,
    }

    # ------------------------------------------------------------------
    # 数据集
    # ------------------------------------------------------------------
    @app.get("/api/datasets")
    def list_datasets():
        return {
            "datasets": dataset_svc.list_datasets(),
            "statuses": dataset_svc.get_all_statuses(),
        }

    @app.get("/api/datasets/{name}")
    def dataset_info(name: str):
        info = dataset_svc.get_info(name)
        if "error" in info:
            raise HTTPException(404, info["error"])
        info["pending_conversion"] = name in dataset_svc.get_pending_conversion()
        return info

    def _dataset_img_url(name: str, server_path: str) -> str | None:
        """服务端绝对路径 → 可访问的 URL（数据集原图）"""
        try:
            rel = (
                Path(server_path)
                .resolve()
                .relative_to((paths.dataset_dir / name / "images" / "train").resolve())
                .as_posix()
            )
            return f"/api/datasets/{name}/images/train/{rel}"
        except ValueError:
            return None

    @app.get("/api/datasets/{name}/preview")
    def dataset_preview(name: str, boxes: bool = False, count: int = 4):
        """样本预览：返回 URL 列表（boxes=true 为画框缓存图）"""
        if boxes:
            urls = [
                f"/api/preview-cache/{name}/{Path(p).name}"
                for p in dataset_svc.get_annotated_samples(name, count=count)
            ]
            return {"images": urls}
        info = dataset_svc.get_info(name)
        if "error" in info:
            raise HTTPException(404, info["error"])
        urls = [u for u in (_dataset_img_url(name, p) for p in info.get("sample_images", [])) if u]
        return {"images": urls}

    @app.get("/api/datasets/{name}/images/{split}/{file_path:path}")
    def dataset_image(name: str, split: str, file_path: str):
        """数据集图像文件（预览用；解析后必须仍在该数据集 images/<split>/ 内）"""
        allowed_root = (paths.dataset_dir / name / "images" / split).resolve()
        img_path = (allowed_root / file_path).resolve()
        if not img_path.is_relative_to(allowed_root) or not img_path.is_file():
            raise HTTPException(404, "Image not found")
        return FileResponse(img_path)

    @app.get("/api/preview-cache/{name}/{file_path:path}")
    def preview_cache_image(name: str, file_path: str):
        """画框预览缓存图（logs/preview_cache/<name>/，带路径校验）"""
        img_path = (paths.logs_dir / "preview_cache" / name / file_path).resolve()
        allowed = (paths.logs_dir / "preview_cache").resolve()
        if not img_path.is_file() or not img_path.is_relative_to(allowed):
            raise HTTPException(404, "Preview not found")
        return FileResponse(img_path)

    @app.post("/api/datasets/upload")
    async def upload_dataset(
        file: UploadFile = File(...),
        name: str = Form(""),
        overwrite: bool = Form(False),
    ):
        if not file.filename or not file.filename.lower().endswith(".zip"):
            raise HTTPException(400, "仅支持 ZIP 文件")
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        try:
            # 命名优先级：显式 name > 上传文件名（而非临时文件名）
            result = dataset_svc.extract(
                tmp_path, name or Path(file.filename).stem, overwrite=overwrite
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)
        status_code = 409 if result["status"] == "exists" else None
        if status_code:
            raise HTTPException(status_code, result["message"])
        if result["status"] == "error":
            raise HTTPException(400, result["message"])
        return result

    @app.post("/api/datasets/{name}/validate")
    def validate_dataset(name: str):
        result = dataset_svc.validate(name)
        if result["status"] == "error" and "不存在" in result.get("message", ""):
            raise HTTPException(404, result["message"])
        return result

    @app.post("/api/datasets/{name}/convert")
    def convert_dataset(name: str, delete_original: bool = False):
        result = dataset_svc.convert(name, delete_original=delete_original)
        if result["status"] == "error":
            raise HTTPException(400, result["message"])
        return result

    # 回收站走 /api/recycle 而不是 /api/datasets/recycle：
    # 后者会被上面已声明的 GET /api/datasets/{name} 抢走匹配（FastAPI 按声明顺序匹配），
    # 于是 "recycle" 被当成一个数据集名去查，永远 404。
    @app.delete("/api/datasets/{name}")
    def delete_dataset(name: str):
        """删除数据集 = 移入回收目录（可恢复），不是直接抹掉"""
        if training_svc.state.is_running:
            # 数据集中途消失会让训练在很晚的阶段炸，且报错和"删数据集"看不出关系
            raise HTTPException(409, "训练进行中，请先停止训练再删除数据集")
        result = dataset_svc.delete(name)
        if result["status"] == "error":
            code = 404 if "不存在" in result.get("message", "") else 400
            raise HTTPException(code, result["message"])
        return result

    @app.get("/api/recycle")
    def list_recycle():
        return {"items": dataset_svc.list_recycled()}

    @app.post("/api/recycle/{recycled_name}/restore")
    def restore_recycle(recycled_name: str):
        result = dataset_svc.restore(recycled_name)
        if result["status"] == "error":
            code = 404 if "不存在" in result.get("message", "") else 400
            raise HTTPException(code, result["message"])
        return result

    # ------------------------------------------------------------------
    # 训练
    # ------------------------------------------------------------------
    def _config_from_request(req: StartTrainingRequest) -> TrainingConfig:
        values = req.model_dump()
        dataset_name = values.pop("dataset_name")
        cfg = TrainingConfig.from_ui(values)
        cfg.dataset_name = dataset_name
        return cfg

    def _resolve_model(cfg: TrainingConfig, allow_download: bool) -> TrainingConfig:
        """清单内模型缺失时的处理：显式允许才同步下载，否则 400（避免请求被大文件下载阻塞）"""
        from src.model_catalog import MODEL_CATALOG

        name = Path(cfg.model).name
        if (paths.basemodels_dir / name).exists() or name not in MODEL_CATALOG:
            return cfg
        if not allow_download:
            raise HTTPException(
                400,
                f"模型 {name} 未下载到 basemodels/。"
                "请先 POST /api/models/download，或设置 download_missing=true。",
            )
        from src.model_downloader import ensure_model

        cfg.model = str(ensure_model(name, base))
        return cfg

    @app.post("/api/trainings/start")
    def start_training(req: StartTrainingRequest):
        if not req.dataset_name or req.dataset_name.startswith("--"):
            raise HTTPException(400, "请先选择数据集")
        cfg = _resolve_model(_config_from_request(req), allow_download=req.download_missing)
        if not training_svc.start(cfg):
            raise HTTPException(409, "训练已在运行中")
        return {"success": True, "task": training_svc.state.task}

    @app.post("/api/trainings/stop")
    def stop_training():
        if not training_svc.stop():
            raise HTTPException(409, "当前没有运行中的训练")
        return {"success": True}

    @app.get("/api/trainings/status")
    def training_status():
        return training_svc.get_status()

    @app.get("/api/trainings/runs")
    def list_runs():
        # checkpoints 由 details 派生，保证两处口径一致（且只扫一次目录）；
        # 排序随之从"路径字典序倒排"变为"最近修改倒排"——后者才真的是"最近的断点在前"
        details = training_svc.list_checkpoint_details()
        return {
            "runs": training_svc.list_runs(),
            "checkpoints": [d["path"] for d in details],
            "checkpoint_details": details,
        }

    @app.get("/api/trainings/results")
    def training_results(run: str | None = None):
        results = training_svc.get_training_results(run)
        if "error" in results:
            raise HTTPException(404, results["error"])
        run_name = results["run_name"]
        results["plot_urls"] = [
            f"/api/trainings/results/{run_name}/plot/{Path(p).name}"
            for p in results.get("result_images", [])
        ]
        results["download_url"] = (
            f"/api/trainings/results/{run_name}/download" if results["has_weights"] else None
        )
        return results

    @app.get("/api/trainings/results/{run}/download")
    def download_best(run: str):
        weights = paths.runs_dir / run / "weights" / "best.pt"
        if not weights.is_file():
            raise HTTPException(404, "best.pt 不存在")
        return FileResponse(weights, filename=f"{run}_best.pt")

    @app.get("/api/trainings/compare")
    def compare_runs(runs: str | None = None):
        run_names = runs.split(",") if runs else None
        return {"markdown": training_svc.compare_runs_markdown(run_names)}

    @app.get("/api/trainings/results/{run}/plot/{filename}")
    def result_plot(run: str, filename: str):
        plot_path = (paths.runs_dir / run / filename).resolve()
        if not is_path_allowed(str(plot_path), ["runs"], base) or not plot_path.is_file():
            raise HTTPException(404, "Plot not found")
        return FileResponse(plot_path)

    # ------------------------------------------------------------------
    # 任务队列
    # ------------------------------------------------------------------
    @app.post("/api/queue/enqueue")
    def enqueue(req: EnqueueRequest):
        cfg = _resolve_model(_config_from_request(req), allow_download=False)
        task_id = task_queue.enqueue(req.dataset_name, asdict(cfg))
        return {"task_id": task_id}

    @app.get("/api/queue/tasks")
    def queue_tasks(limit: int = 50):
        return {"tasks": task_queue.list_tasks(limit=limit)}

    @app.post("/api/queue/{task_id}/cancel")
    def cancel_task(task_id: int):
        if not task_queue.cancel(task_id):
            raise HTTPException(409, "任务不存在或已结束")
        return {"success": True}

    # ------------------------------------------------------------------
    # 模型清单 / 注册表 / 导出
    # ------------------------------------------------------------------
    @app.get("/api/models")
    def model_catalog(task: str | None = None):
        from src.model_catalog import MODEL_CATALOG, list_available_models
        from src.model_downloader import is_model_downloaded

        entries = list_available_models(task=task) if task else list(MODEL_CATALOG.values())
        return {
            "models": [
                {
                    "filename": e.filename,
                    "family": e.family.value,
                    "size": e.size,
                    "task": e.task,
                    "local": is_model_downloaded(e.filename, base),
                    "size_mb": e.size_mb,
                }
                for e in entries
            ]
        }

    @app.post("/api/models/download")
    def download_model(filename: str = Form(...)):
        from src.model_catalog import MODEL_CATALOG
        from src.model_downloader import ensure_model

        if Path(filename).name not in MODEL_CATALOG:
            raise HTTPException(400, f"未知模型: {filename}")
        try:
            path = ensure_model(Path(filename).name, base)
        except Exception as e:
            raise HTTPException(502, f"下载失败: {e}") from e
        return {"success": True, "path": str(path)}

    # ------------------------------------------------------------------
    # 模型注册表（读 + 写）
    #
    # ModelRegistry 的读写方法早就在，但此前只暴露了一个只读列表 ——
    # 控制台看得到版本却动不了，等价于一个只能看不能用的注册中心。
    # 注意：每个请求都新建实例，直接读盘上的 versions.json，
    # 这样训练进程刚注册的版本立刻可见（训练跑在另一个进程里）。
    # ------------------------------------------------------------------
    REGISTRY_STATUSES = ("staging", "production", "archived")

    def _registry():
        from src.model_registry import ModelRegistry

        return ModelRegistry(str(base))

    def _require_version(reg, dataset: str, version_id: str):
        version = reg.get_version(dataset, version_id)
        if version is None:
            raise HTTPException(404, f"版本不存在: {dataset}/{version_id}")
        return version

    @app.get("/api/registry")
    def registry_all():
        return {"datasets": _registry().list_all()}

    @app.get("/api/registry/{dataset}")
    def registry_versions(dataset: str):
        reg = _registry()
        versions = reg.get_versions(dataset)
        if not versions:
            raise HTTPException(404, f"数据集 {dataset} 没有注册版本")
        return {
            "dataset": dataset,
            "versions": [v.to_dict() for v in versions],
            "production_model": reg.get_production_model(dataset),
        }

    @app.post("/api/registry/register")
    def registry_register(req: RegisterModelRequest):
        dataset_name = req.dataset_name.strip()
        if not dataset_name:
            raise HTTPException(400, "请填写数据集名称")

        if req.model_path:
            if not is_path_allowed(req.model_path, ["runs", "basemodels", "exports"], base):
                raise HTTPException(400, "model_path 必须位于 runs/、basemodels/ 或 exports/ 之下")
            weights = Path(req.model_path)
        elif req.run_name:
            if req.weights not in ("best", "last"):
                raise HTTPException(400, "weights 只能是 best 或 last")
            weights = paths.runs_dir / req.run_name / "weights" / f"{req.weights}.pt"
            # run_name 由请求体给出，可能含 ../ —— 解析后必须仍在 runs/ 内
            if not is_path_allowed(str(weights), ["runs"], base):
                raise HTTPException(400, "run 名称非法")
        else:
            raise HTTPException(400, "请提供 run_name 或 model_path")

        if not weights.is_file():
            raise HTTPException(404, f"权重文件不存在: {weights}")

        metrics = dict(req.metrics or {})
        if not metrics and req.run_name:
            # 自动补最终指标；results.csv 缺失或读不出时保持空，不编造数字。
            # 只留 mAP50 / mAP50_95 两个规范键：注册表的 get_best 与前端都按
            # 这两个键取数，多塞一套 "mAP@50" 同义键只会让对比表出现重复行。
            final = training_svc.get_training_results(req.run_name).get("final_metrics") or {}
            metrics = {
                k: float(final[k])
                for k in ("mAP50", "mAP50_95")
                if isinstance(final.get(k), (int, float))
            }

        try:
            version = _registry().register(
                model_path=str(weights),
                dataset_name=dataset_name,
                metrics=metrics,
                tags=[t.strip() for t in req.tags if t and t.strip()],
                description=req.description,
                copy_model=req.copy_model,
            )
        except OSError as e:
            raise HTTPException(500, f"注册失败（写入 model_registry/）: {e}") from e

        if req.metrics:
            metrics_source = "request"
        elif metrics:
            metrics_source = "results.csv"
        else:
            metrics_source = "none"
        return {
            "success": True,
            "version": version.to_dict(),
            "metrics_auto_filled": metrics_source == "results.csv",
            "metrics_source": metrics_source,
        }

    @app.post("/api/registry/{dataset}/{version_id}/status")
    def registry_set_status(dataset: str, version_id: str, req: VersionStatusRequest):
        if req.status not in REGISTRY_STATUSES:
            raise HTTPException(400, "status 只能是 " + " / ".join(REGISTRY_STATUSES))
        reg = _registry()
        _require_version(reg, dataset, version_id)
        reg.update_status(dataset, version_id, req.status)
        return {"success": True, "status": req.status}

    @app.post("/api/registry/{dataset}/{version_id}/promote")
    def registry_promote(dataset: str, version_id: str):
        """晋升为生产版本（该数据集原有的生产版本会自动转为 archived）"""
        reg = _registry()
        _require_version(reg, dataset, version_id)
        reg.promote_to_production(dataset, version_id)
        versions = reg.get_versions(dataset)
        return {
            "success": True,
            "production_model": reg.get_production_model(dataset),
            "archived": [v.version_id for v in versions if v.status == "archived"],
        }

    @app.post("/api/registry/{dataset}/{version_id}/tags")
    def registry_add_tags(dataset: str, version_id: str, req: VersionTagsRequest):
        tags = [t.strip() for t in req.tags if t and t.strip()]
        if not tags:
            raise HTTPException(400, "请提供至少一个非空标签")
        reg = _registry()
        _require_version(reg, dataset, version_id)
        reg.add_tags(dataset, version_id, tags)
        return {"success": True, "tags": reg.get_version(dataset, version_id).tags}

    @app.get("/api/registry/{dataset}/compare")
    def registry_compare(dataset: str, a: str, b: str):
        result = _registry().compare_versions(dataset, a, b)
        if "error" in result:
            raise HTTPException(404, result["error"])
        return result

    @app.delete("/api/registry/{dataset}/{version_id}")
    def registry_delete(dataset: str, version_id: str):
        """删除注册记录。

        只动注册表：`copy_model=False` 注册的版本，权重留在 runs/ 原位不受影响；
        `copy_model=True` 的版本，注册表内那份副本会被删除（原位权重同样保留）。
        """
        reg = _registry()
        version = _require_version(reg, dataset, version_id)
        if version.status == "production":
            # 直接删会让 get_production_model 静默变 None，调用方无从察觉
            raise HTTPException(409, "生产版本不能直接删除：请先把别的版本设为生产，或改为归档")

        kept_path = Path(version.model_path)
        deleted_copy = kept_path.is_relative_to(reg.models_dir.resolve())
        reg.delete_version(dataset, version_id)
        return {
            "success": True,
            "deleted_registry_copy": deleted_copy,
            "weights_path": None if deleted_copy else version.model_path,
        }

    @app.post("/api/exports")
    def export_model(req: ExportRequest):
        weights = paths.runs_dir / req.run_name / "weights" / "best.pt"
        if not weights.exists():
            raise HTTPException(404, f"best.pt 不存在: run={req.run_name}")
        try:
            from src.model_exporter import ModelExporter

            report = ModelExporter(str(base)).export(model_path=str(weights), formats=[req.fmt])
        except Exception as e:
            raise HTTPException(500, f"导出失败: {e}") from e
        r = report.results[0] if report.results else None
        if r is None or not r.success:
            raise HTTPException(500, (r.message if r else "导出失败"))
        return {
            "success": True,
            "format": r.format,
            "path": r.output_path,
            "size_mb": round(r.file_size / (1024 * 1024), 2),
        }

    # ------------------------------------------------------------------
    # WebSocket：训练状态 + 日志流（每秒推送，替代 Gradio Timer 轮询）
    # ------------------------------------------------------------------
    @app.websocket("/ws/training")
    async def training_stream(ws: WebSocket):
        await ws.accept()
        try:
            while True:
                status = training_svc.get_status()
                await ws.send_text(
                    json.dumps(
                        {"type": "training", "status": status, "logs": status.pop("logs", "")},
                        ensure_ascii=False,
                        default=str,
                    )
                )
                await asyncio.sleep(1.0)
        except (WebSocketDisconnect, RuntimeError):
            return
        except Exception:
            logger.debug("[WS] training stream closed", exc_info=True)
            return

    @app.get("/api/health")
    def health():
        return {"status": "ok", "model_loaded": training_svc.state.is_running}

    # ------------------------------------------------------------------
    # 前端静态托管（vite build 产物存在时，SPA 回退到 index.html）
    # ------------------------------------------------------------------
    dist = Path(frontend_dist) if frontend_dist else PROJECT_ROOT / "frontend" / "dist"
    if dist.exists():
        app.mount("/", SPAStaticFiles(directory=str(dist), html=True), name="frontend")
    else:

        @app.get("/")
        async def index():
            return JSONResponse(
                {
                    "service": "AYT Admin API",
                    "hint": "前端未构建：cd frontend && pnpm install && pnpm build",
                    "api_docs": "/api/docs",
                }
            )

    return app


def main():
    """CLI 入口：ayt-web / python -m src.api.admin"""
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="AYT 管理面 API + 前端")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(create_admin_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
