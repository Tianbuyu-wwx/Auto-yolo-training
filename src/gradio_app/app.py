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
from src.gradio_app.components.queue_panel import build_queue_panel
from src.gradio_app.components.result_viewer import build_result_viewer
from src.gradio_app.components.training_monitor import build_training_monitor
from src.gradio_app.models.training_state import TrainingConfig
from src.gradio_app.services.dataset_service import DatasetService
from src.gradio_app.services.log_service import LogService
from src.gradio_app.services.training_service import TrainingService
from src.gradio_app.theme import create_theme
from src.task_queue import QueueRunner, TaskQueue
from src.utils import is_path_allowed

logger = logging.getLogger(__name__)

# 开始训练按钮的 inputs 顺序（cfg_components 的键）；与 on_start_training 的 *param_values 一一对应
_CONFIG_PARAM_ORDER = [
    "task", "model", "epochs", "imgsz", "batch", "lr0", "optimizer",
    "cos_lr", "lrf", "warmup_epochs", "patience", "cache", "rect",
    "deterministic", "freeze", "dropout", "label_smoothing", "weight_decay",
    "box", "cls", "dfl", "copy_paste", "close_mosaic", "mosaic", "mixup",
    "degrees", "scale", "translate", "shear", "perspective", "flipud",
    "hsv_h", "hsv_s", "hsv_v", "device", "workers", "skip_validation",
]


def create_app(css: str = ""):
    """创建Gradio应用"""

    base_dir = Path(__file__).parent.parent.parent
    log_svc = LogService()
    dataset_svc = DatasetService(base_dir)
    training_svc = TrainingService(base_dir, log_svc)
    # 任务队列（P3-2）：SQLite 持久化 + 后台 runner（子进程执行任务）
    task_queue = TaskQueue(base_dir / "logs" / "task_queue.db")
    queue_runner = QueueRunner(task_queue, base_dir)
    queue_runner.start()

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

            with gr.Tab("⑤ 队列"):
                _queue_components = build_queue_panel(task_queue, queue_runner)

        # ====== 全局事件绑定 ======

        # 刷新数据集列表
        def on_refresh_datasets():
            datasets = dataset_svc.list_datasets()
            choices = ["-- 请选择 --"] + datasets
            return gr.update(choices=choices, value=choices[0])

        refresh_ds_btn.click(fn=on_refresh_datasets, outputs=[dataset_dropdown])

        # 页面加载时刷新
        demo.load(fn=on_refresh_datasets, outputs=[dataset_dropdown])

        # 开始训练：inputs 顺序由 _CONFIG_PARAM_ORDER 定义，
        # 参数值打包成 dict 后经 TrainingConfig.from_ui 构造（类型自动转换）
        # 末尾两个 inputs 是断点续训组件（P2-4）
        def on_start_training(dataset_name, *param_values):
            resume_enabled, resume_ckpt = param_values[-2:]
            param_values = param_values[:-2]

            if not dataset_name or dataset_name.startswith("--"):
                return gr.update(
                    value='<div class="status-indicator"><span class="status-dot error"></span>请先选择数据集</div>'
                ), gr.update(interactive=True), gr.update(interactive=False)

            values = dict(zip(_CONFIG_PARAM_ORDER, param_values, strict=True))

            # 断点续训：模型换成 last.pt，跳过重复校验
            if resume_enabled and resume_ckpt:
                values["model"] = resume_ckpt
                values["skip_validation"] = True
            else:
                values["skip_validation"] = bool(values.get("skip_validation"))

            # 解析模型路径
            try:
                model_path = _resolve_model_path(values["model"], base_dir)
            except ValueError as e:
                logger.warning("[APP] 模型路径校验失败: %s", e)
                return gr.update(
                    value=f'<div class="status-indicator"><span class="status-dot error"></span>{e}</div>'
                ), gr.update(interactive=True), gr.update(interactive=False)

            # 清单中的模型若未下载，先下载到 basemodels/
            # （否则 Ultralytics 会把权重下到 CWD，绕过统一管理）
            try:
                model_path = _ensure_model_available(model_path, base_dir)
            except Exception as e:
                logger.warning("[APP] 模型下载失败: %s", e)
                return gr.update(
                    value=f'<div class="status-indicator"><span class="status-dot error"></span>模型下载失败: {e}</div>'
                ), gr.update(interactive=True), gr.update(interactive=False)

            values["model"] = model_path
            config = TrainingConfig.from_ui({**values, "dataset_name": dataset_name})
            if resume_enabled and resume_ckpt:
                config.resume_from = str(resume_ckpt)

            success = training_svc.start(config)
            if success:
                return gr.update(
                    value='<div class="status-indicator"><span class="status-dot running"></span>训练已启动</div>'
                ), gr.update(interactive=False), gr.update(interactive=True)
            else:
                return gr.update(
                    value='<div class="status-indicator"><span class="status-dot error"></span>训练已在运行中</div>'
                ), gr.update(), gr.update()

        train_inputs = (
            [dataset_dropdown]
            + [cfg_components[k] for k in _CONFIG_PARAM_ORDER]
            + [monitor_components["resume_checkbox"], monitor_components["resume_dropdown"]]
        )

        monitor_components["start_btn"].click(
            fn=on_start_training,
            inputs=train_inputs,
            outputs=[
                monitor_components.get("status_html", gr.HTML()),
                monitor_components["start_btn"],
                monitor_components["stop_btn"],
            ],
        )

        # 加入队列（P3-2）：不立即执行，交给 SQLite 队列按顺序跑
        def on_enqueue_training(dataset_name, *param_values):
            resume_enabled, resume_ckpt = param_values[-2:]
            param_values = param_values[:-2]

            if not dataset_name or dataset_name.startswith("--"):
                return gr.update(value="❌ 请先在顶部选择数据集", visible=True)

            values = dict(zip(_CONFIG_PARAM_ORDER, param_values, strict=True))
            if resume_enabled and resume_ckpt:
                values["model"] = resume_ckpt

            try:
                model_path = _ensure_model_available(
                    _resolve_model_path(values.get("model", ""), base_dir), base_dir,
                )
            except Exception as e:
                return gr.update(value=f"❌ 模型不可用: {e}", visible=True)

            values["model"] = model_path
            config = TrainingConfig.from_ui({**values, "dataset_name": dataset_name})
            if resume_enabled and resume_ckpt:
                config.resume_from = str(resume_ckpt)

            from dataclasses import asdict

            task_id = task_queue.enqueue(dataset_name, asdict(config))
            return gr.update(
                value=f"✅ 已加入队列（任务 #{task_id}）。进度见「⑤ 队列」页。",
                visible=True,
            )

        monitor_components["queue_btn"].click(
            fn=on_enqueue_training,
            inputs=train_inputs,
            outputs=[monitor_components["queue_status_md"]],
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

        # 训练结束联动：timer 检测到完成信号后自动刷新结果页
        def _refresh_results_if_finished(finished_signal):
            outputs = _result_components["outputs"]
            if not finished_signal:
                return [gr.update()] * len(outputs)
            return list(_result_components["refresh_fn"]())

        monitor_components["tick_event"].then(
            fn=_refresh_results_if_finished,
            inputs=[monitor_components["finished_signal"]],
            outputs=_result_components["outputs"],
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


def _ensure_model_available(model_path: str, base_dir: Path) -> str:
    """清单内的模型若未下载则先下载到 basemodels/，返回可用路径。

    非 bare 文件名（如完整路径）或下载失败时原样返回/抛错。
    """
    from src.model_catalog import MODEL_CATALOG
    from src.model_downloader import ensure_model, is_model_downloaded

    name = Path(model_path).name
    if name not in MODEL_CATALOG:
        return model_path
    if is_model_downloaded(name, base_dir):
        return str(base_dir / "basemodels" / name)
    logger.info("[APP] 模型未下载，开始下载: %s", name)
    downloaded = ensure_model(name, base_dir)
    return str(downloaded)


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
    parser.add_argument(
        "--auth",
        default=None,
        help='登录凭据 "user:pass"（多用户逗号分隔）；默认读取 YOLO_GRADIO__AUTH，未配置则无认证',
    )

    args = parser.parse_args()

    _startup_dataset_management()

    # P3-5：认证（settings 优先，CLI 覆盖）。公网/多用户部署务必配置。
    from src.settings import get_settings

    settings = get_settings()
    credentials = settings.gradio_auth_credentials()
    if args.auth is not None:
        settings.gradio.auth = args.auth
        credentials = settings.gradio_auth_credentials()
    if credentials:
        logger.info("[AUTH] Gradio 认证已启用（%d 个用户）", len(credentials))
    elif args.host in ("0.0.0.0", "::") or args.share:
        logger.warning(
            "[AUTH] 服务暴露到公网但未配置认证！"
            "建议设置 YOLO_GRADIO__AUTH=\"user:pass\" 或使用 --auth user:pass"
        )

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
        auth=credentials,
    )


if __name__ == "__main__":
    main()
