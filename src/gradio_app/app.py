"""
YOLO自动训练平台 — 主入口
Tab式工作流：数据集 → 配置 → 训练 → 结果
"""

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import gradio as gr

from src.dataset_manager import AutoDatasetManager, DatasetFormat
from src.gradio_app.components.config_panel import build_config_panel
from src.gradio_app.components.dataset_panel import build_dataset_panel
from src.gradio_app.components.result_viewer import build_result_viewer
from src.gradio_app.components.training_monitor import build_training_monitor
from src.gradio_app.models.training_state import TrainingConfig
from src.gradio_app.services.dataset_service import DatasetService
from src.gradio_app.services.log_service import LogService
from src.gradio_app.services.training_service import TrainingService
from src.gradio_app.theme import create_theme
from src.utils import is_path_allowed

logger = logging.getLogger(__name__)


def create_app(css: str = ""):
    """创建Gradio应用"""

    base_dir = Path(__file__).parent.parent.parent
    log_svc = LogService()
    dataset_svc = DatasetService(base_dir)
    training_svc = TrainingService(base_dir, log_svc)

    with gr.Blocks(
        title="YOLO 自动训练平台",
        theme=create_theme(),
        css=css,
    ) as demo:

        gr.HTML('<h1 class="app-title">YOLO <span>Auto Training</span></h1>')

        # 数据集选择（全局共享，跨Tab使用）
        with gr.Row():
            dataset_dropdown = gr.Dropdown(
                choices=["-- 请选择 --"],
                value="-- 请选择 --",
                label="当前数据集",
                interactive=True,
                scale=3,
            )
            refresh_ds_btn = gr.Button("刷新", size="sm", scale=1)

        # Tab工作流
        with gr.Tabs():
            with gr.Tab("① 数据集"):
                _ds_components = build_dataset_panel(dataset_svc, dataset_dropdown)

            with gr.Tab("② 配置"):
                cfg_components = build_config_panel(dataset_svc)

            with gr.Tab("③ 训练"):
                monitor_components = build_training_monitor(training_svc, log_svc)

            with gr.Tab("④ 结果"):
                _result_components = build_result_viewer(training_svc)

        # ====== 全局事件绑定 ======

        # 刷新数据集列表
        def on_refresh_datasets():
            datasets = dataset_svc.list_datasets()
            choices = ["-- 请选择 --"] + datasets
            return gr.update(choices=choices, value=choices[0])

        refresh_ds_btn.click(fn=on_refresh_datasets, outputs=[dataset_dropdown])

        # 页面加载时刷新
        demo.load(fn=on_refresh_datasets, outputs=[dataset_dropdown])

        # 开始训练（使用TrainingConfig替代15个参数）
        def on_start_training(
            dataset_name, model, epochs, imgsz, batch, lr0, optimizer,
            cos_lr, lrf, warmup_epochs, patience,
            cache, rect, deterministic, freeze,
            dropout, label_smoothing, weight_decay,
            box, cls, dfl, copy_paste, close_mosaic,
            mosaic, mixup, degrees, scale, translate,
            shear, perspective, flipud,
            hsv_h, hsv_s, hsv_v,
            device, workers, skip_validation,
        ):
            if not dataset_name or dataset_name.startswith("--"):
                return gr.update(
                    value='<div class="status-indicator"><span class="status-dot error"></span>请先选择数据集</div>'
                ), gr.update(interactive=True), gr.update(interactive=False)

            # 解析模型路径
            try:
                model_path = _resolve_model_path(model, base_dir)
            except ValueError as e:
                logger.warning("[APP] 模型路径校验失败: %s", e)
                return gr.update(
                    value=f'<div class="status-indicator"><span class="status-dot error"></span>{e}</div>'
                ), gr.update(interactive=True), gr.update(interactive=False)

            # cache 下拉框特殊处理："None" -> None
            cache_value = None if cache == "None" else cache
            # device UI 翻译："auto (recommended)" / "cpu" / "0" / "1" → Ultralytics 接受的字符串
            # Ultralytics 不接受 "auto"——空字符串才是自动检测
            device_value = "" if device and device.startswith("auto") else device

            config = TrainingConfig(
                dataset_name=dataset_name,
                model=model_path,
                epochs=int(epochs),
                imgsz=int(imgsz),
                batch=int(batch),
                device=device_value,
                workers=int(workers),
                lr0=float(lr0),
                optimizer=optimizer,
                cos_lr=bool(cos_lr),
                lrf=float(lrf),
                warmup_epochs=float(warmup_epochs),
                patience=int(patience),
                dropout=float(dropout),
                mosaic=float(mosaic),
                mixup=float(mixup),
                degrees=float(degrees),
                scale=float(scale),
                translate=float(translate),
                shear=float(shear),
                perspective=float(perspective),
                flipud=float(flipud),
                hsv_h=float(hsv_h),
                hsv_s=float(hsv_s),
                hsv_v=float(hsv_v),
                cache=cache_value,
                rect=bool(rect),
                deterministic=bool(deterministic),
                freeze=int(freeze),
                label_smoothing=float(label_smoothing),
                weight_decay=float(weight_decay),
                box=float(box),
                cls=float(cls),
                dfl=float(dfl),
                copy_paste=float(copy_paste),
                close_mosaic=int(close_mosaic),
                skip_validation=bool(skip_validation),
            )

            success = training_svc.start(config)
            if success:
                return gr.update(
                    value='<div class="status-indicator"><span class="status-dot running"></span>训练已启动</div>'
                ), gr.update(interactive=False), gr.update(interactive=True)
            else:
                return gr.update(
                    value='<div class="status-indicator"><span class="status-dot error"></span>训练已在运行中</div>'
                ), gr.update(), gr.update()

        monitor_components["start_btn"].click(
            fn=on_start_training,
            inputs=[
                dataset_dropdown,
                cfg_components["model"],
                cfg_components["epochs"],
                cfg_components["imgsz"],
                cfg_components["batch"],
                cfg_components["lr0"],
                cfg_components["optimizer"],
                cfg_components["cos_lr"],
                cfg_components["lrf"],
                cfg_components["warmup_epochs"],
                cfg_components["patience"],
                cfg_components["cache"],
                cfg_components["rect"],
                cfg_components["deterministic"],
                cfg_components["freeze"],
                cfg_components["dropout"],
                cfg_components["label_smoothing"],
                cfg_components["weight_decay"],
                cfg_components["box"],
                cfg_components["cls"],
                cfg_components["dfl"],
                cfg_components["copy_paste"],
                cfg_components["close_mosaic"],
                cfg_components["mosaic"],
                cfg_components["mixup"],
                cfg_components["degrees"],
                cfg_components["scale"],
                cfg_components["translate"],
                cfg_components["shear"],
                cfg_components["perspective"],
                cfg_components["flipud"],
                cfg_components["hsv_h"],
                cfg_components["hsv_s"],
                cfg_components["hsv_v"],
                cfg_components["device"],
                cfg_components["workers"],
                cfg_components["skip_validation"],
            ],
            outputs=[
                monitor_components.get("status_html", gr.HTML()),
                monitor_components["start_btn"],
                monitor_components["stop_btn"],
            ],
        )

        # 停止训练
        def on_stop_training():
            training_svc.stop()
            return gr.update(interactive=True), gr.update(interactive=False)

        monitor_components["stop_btn"].click(
            fn=on_stop_training,
            outputs=[
                monitor_components["start_btn"],
                monitor_components["stop_btn"],
            ],
        )

    return demo


def _resolve_model_path(model_name: str, base_dir: Path) -> str:
    """解析模型路径，并校验路径安全"""
    if not model_name:
        return model_name

    # 若传入完整路径，校验其在允许目录内
    if Path(model_name).is_absolute() or len(Path(model_name).parts) > 1:
        if not is_path_allowed(model_name, ["basemodels", "runs"], base_dir):
            raise ValueError(f"模型路径不在允许目录内: {model_name}")
        return model_name

    basemodels_dir = base_dir / "basemodels"
    model_path = basemodels_dir / model_name
    if model_path.exists():
        return str(model_path)
    return model_name


def _startup_dataset_management():
    """启动时执行一次的数据集扫描（不自动转换/删除原始数据）。

    设计变更（2026-09-02）：移除 Gradio 启动时的自动分类→YOLO 转换 + 删除原始数据集。
    原行为存在数据丢失隐患——任何启动 Gradio 的用户，其分类格式数据集都会被
    静默转换并删除原目录。改为：仅扫描 + 报告需要转换的数据集，
    由用户在 Gradio ① 数据集 Tab 显式触发转换（dataset_panel 已预留入口）。
    """
    try:
        base_dir = Path(__file__).parent.parent.parent
        dataset_dir = base_dir / "dataset"
        logger.info("[SCAN] 开始扫描数据集: %s", dataset_dir)

        dataset_manager = AutoDatasetManager(str(dataset_dir))
        datasets = dataset_manager.scan_all_datasets()

        yolo_count = sum(1 for ds in datasets if ds.format == DatasetFormat.YOLO)
        classification_count = sum(1 for ds in datasets if ds.needs_conversion)

        logger.info("[SCAN] 扫描完成: 总计 %d 个 (YOLO=%d, 待转换=%d)",
                    len(datasets), yolo_count, classification_count)

        if classification_count > 0:
            pending = [ds.name for ds in datasets if ds.needs_conversion]
            logger.warning(
                "[SCAN] 检测到 %d 个待转换数据集: %s。"
                "请在 Gradio ① 数据集 Tab 手动触发转换（已禁用启动自动转换以防数据丢失）。",
                classification_count, pending,
            )
    except Exception as e:
        logger.error("[SCAN] 数据集扫描失败: %s", e)


def main():
    """主入口"""
    import argparse

    # 禁用 Gradio telemetry / 版本检查，避免无网络环境报错
    os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

    parser = argparse.ArgumentParser(description="YOLO自动训练平台 - Gradio界面")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=7860, help="端口")
    parser.add_argument("--share", action="store_true", help="生成公网分享链接")

    args = parser.parse_args()

    _startup_dataset_management()

    css_path = Path(__file__).parent / "styles.css"
    css = css_path.read_text(encoding="utf-8") if css_path.exists() else ""

    app = create_app(css=css)
    app.launch(
        server_name=args.host,
        server_port=args.port,
        share=args.share,
        show_error=True,
        show_api=False,
        quiet=True,
        inbrowser=False,
    )


if __name__ == "__main__":
    main()
