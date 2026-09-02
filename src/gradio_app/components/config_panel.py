"""
训练参数配置面板组件
含预设系统
"""

import gradio as gr
from pathlib import Path
from typing import Dict, Any

from src.gradio_app.models.training_state import TrainingConfig, PRESETS
from src.gradio_app.services.dataset_service import DatasetService


def build_config_panel(dataset_svc: DatasetService = None):
    """构建训练参数配置Tab"""

    with gr.Row():
        # 左侧：参数预设
        with gr.Column(scale=1, min_width=260):
            gr.Markdown("### 参数预设")
            preset_radio = gr.Radio(
                choices=list(PRESETS.keys()) + ["自定义"],
                value="标准训练",
                label="",
                interactive=True,
            )
            gr.Markdown(
                "快速验证: 50ep / 416px\n\n"
                "标准训练: 150ep / 640px\n\n"
                "精细调优: 300ep / 640px"
            )

        # 右侧：参数面板
        with gr.Column(scale=2):
            gr.Markdown("### 基础参数")

            with gr.Row():
                model_dropdown = gr.Dropdown(
                    choices=_get_model_choices(),
                    value=_get_model_choices()[0] if _get_model_choices() else "yolov8s.pt",
                    label="预训练模型",
                )
                device_dropdown = gr.Dropdown(
                    choices=["auto (recommended)", "cpu", "0", "1"],
                    value="auto (recommended)",  # 通用化：让 Ultralytics 自动检测；UI 翻译为 device=""
                    label="训练设备",
                )

            with gr.Row():
                epochs_slider = gr.Slider(
                    minimum=10, maximum=500, value=150, step=10,
                    label="训练轮数 (Epochs)",
                )
                imgsz_dropdown = gr.Dropdown(
                    choices=[320, 416, 512, 640, 768, 896, 1024, 1280],
                    value=640,
                    label="输入图像尺寸",
                )

            with gr.Row():
                batch_dropdown = gr.Dropdown(
                    choices=[2, 4, 8, 16, 32, 64],
                    value=16,
                    label="批次大小 (Batch)",
                )
                workers_slider = gr.Slider(
                    minimum=0, maximum=16, value=8, step=1,
                    label="数据加载线程数",
                )

            with gr.Accordion("高级参数", open=False):
                with gr.Row():
                    lr0_slider = gr.Slider(
                        minimum=0.0001, maximum=0.01, value=0.001, step=0.0001,
                        label="初始学习率 (lr0)",
                    )
                    optimizer_dropdown = gr.Dropdown(
                        choices=["AdamW", "SGD", "Adam", "NAdam", "RAdam", "RMSProp"],
                        value="AdamW",
                        label="优化器",
                    )

                with gr.Row():
                    cos_lr_checkbox = gr.Checkbox(
                        value=True,
                        label="余弦退火学习率 (Cosine Annealing)",
                    )
                    lrf_slider = gr.Slider(
                        minimum=0.001, maximum=0.1, value=0.01, step=0.001,
                        label="最终学习率因子 (lrf)",
                    )

                with gr.Row():
                    warmup_epochs_slider = gr.Slider(
                        minimum=0.0, maximum=10.0, value=3.0, step=0.5,
                        label="预热轮数 (Warmup Epochs)",
                    )
                    patience_slider = gr.Slider(
                        minimum=5, maximum=100, value=30, step=5,
                        label="早停耐心值 (Patience)",
                    )

                with gr.Row():
                    cache_dropdown = gr.Dropdown(
                        choices=["None", "ram", "disk"],
                        value="disk",
                        label="数据缓存 (Cache)",
                    )
                    rect_checkbox = gr.Checkbox(
                        value=True,
                        label="矩形训练 (Rect)",
                    )

                with gr.Row():
                    deterministic_checkbox = gr.Checkbox(
                        value=False,
                        label="确定性训练 (Deterministic)",
                    )
                    freeze_slider = gr.Slider(
                        minimum=0, maximum=20, value=0, step=1,
                        label="冻结层数 (Freeze)",
                    )

                with gr.Row():
                    dropout_slider = gr.Slider(
                        minimum=0.0, maximum=0.5, value=0.0, step=0.05,
                        label="Dropout",
                    )
                    label_smoothing_slider = gr.Slider(
                        minimum=0.0, maximum=0.2, value=0.0, step=0.01,
                        label="标签平滑 (Label Smoothing)",
                    )

                with gr.Row():
                    weight_decay_slider = gr.Slider(
                        minimum=0.0001, maximum=0.001, value=0.0005, step=0.0001,
                        label="权重衰减 (Weight Decay)",
                    )
                    copy_paste_slider = gr.Slider(
                        minimum=0.0, maximum=0.3, value=0.0, step=0.05,
                        label="Copy-Paste 增强",
                    )

                with gr.Row():
                    box_slider = gr.Slider(
                        minimum=1.0, maximum=15.0, value=7.5, step=0.5,
                        label="Box 损失权重",
                    )
                    cls_slider = gr.Slider(
                        minimum=0.1, maximum=2.0, value=0.5, step=0.1,
                        label="Cls 损失权重",
                    )

                with gr.Row():
                    dfl_slider = gr.Slider(
                        minimum=0.5, maximum=3.0, value=1.5, step=0.1,
                        label="DFL 损失权重",
                    )
                    close_mosaic_slider = gr.Slider(
                        minimum=0, maximum=50, value=10, step=1,
                        label="关闭 Mosaic 轮数",
                    )

                with gr.Row():
                    mosaic_slider = gr.Slider(
                        minimum=0.0, maximum=1.0, value=1.0, step=0.1,
                        label="Mosaic 增强",
                    )
                    mixup_slider = gr.Slider(
                        minimum=0.0, maximum=1.0, value=0.0, step=0.1,
                        label="Mixup 增强",
                    )

                with gr.Row():
                    degrees_slider = gr.Slider(
                        minimum=0.0, maximum=45.0, value=0.0, step=1.0,
                        label="旋转角度 (Degrees)",
                    )
                    scale_slider = gr.Slider(
                        minimum=0.1, maximum=1.0, value=0.5, step=0.1,
                        label="缩放比例 (Scale)",
                    )

                with gr.Row():
                    translate_slider = gr.Slider(
                        minimum=0.0, maximum=0.5, value=0.1, step=0.05,
                        label="平移 (Translate)",
                    )
                    shear_slider = gr.Slider(
                        minimum=0.0, maximum=20.0, value=0.0, step=1.0,
                        label="剪切 (Shear)",
                    )

                with gr.Row():
                    perspective_slider = gr.Slider(
                        minimum=0.0, maximum=0.001, value=0.0, step=0.0001,
                        label="透视 (Perspective)",
                    )
                    flipud_slider = gr.Slider(
                        minimum=0.0, maximum=1.0, value=0.0, step=0.1,
                        label="上下翻转 (FlipUD)",
                    )

                with gr.Row():
                    hsv_h_slider = gr.Slider(
                        minimum=0.0, maximum=0.1, value=0.015, step=0.005,
                        label="HSV-H 色调",
                    )
                    hsv_s_slider = gr.Slider(
                        minimum=0.0, maximum=1.0, value=0.7, step=0.1,
                        label="HSV-S 饱和度",
                    )

                with gr.Row():
                    hsv_v_slider = gr.Slider(
                        minimum=0.0, maximum=1.0, value=0.4, step=0.1,
                        label="HSV-V 明度",
                    )

            skip_validation_checkbox = gr.Checkbox(
                value=False,
                label="跳过数据验证（已知数据正常时）",
            )

    # --- 预设切换 ---

    def on_preset_selected(preset_name: str):
        preset = PRESETS.get(preset_name, {})
        return (
            gr.update(value=preset.get("epochs", 150)),
            gr.update(value=preset.get("batch", 16)),
            gr.update(value=preset.get("imgsz", 640)),
            gr.update(value=preset.get("patience", 30)),
            gr.update(value=preset.get("lr0", 0.001)),
        )

    preset_radio.change(
        fn=on_preset_selected,
        inputs=[preset_radio],
        outputs=[epochs_slider, batch_dropdown, imgsz_dropdown,
                 patience_slider, lr0_slider],
    )

    return {
        "model": model_dropdown,
        "device": device_dropdown,
        "epochs": epochs_slider,
        "imgsz": imgsz_dropdown,
        "batch": batch_dropdown,
        "workers": workers_slider,
        "lr0": lr0_slider,
        "optimizer": optimizer_dropdown,
        "cos_lr": cos_lr_checkbox,
        "lrf": lrf_slider,
        "warmup_epochs": warmup_epochs_slider,
        "patience": patience_slider,
        "dropout": dropout_slider,
        "mosaic": mosaic_slider,
        "mixup": mixup_slider,
        "degrees": degrees_slider,
        "scale": scale_slider,
        "translate": translate_slider,
        "shear": shear_slider,
        "perspective": perspective_slider,
        "flipud": flipud_slider,
        "hsv_h": hsv_h_slider,
        "hsv_s": hsv_s_slider,
        "hsv_v": hsv_v_slider,
        "cache": cache_dropdown,
        "rect": rect_checkbox,
        "deterministic": deterministic_checkbox,
        "freeze": freeze_slider,
        "label_smoothing": label_smoothing_slider,
        "weight_decay": weight_decay_slider,
        "box": box_slider,
        "cls": cls_slider,
        "dfl": dfl_slider,
        "copy_paste": copy_paste_slider,
        "close_mosaic": close_mosaic_slider,
        "skip_validation": skip_validation_checkbox,
    }


def _get_model_choices():
    """获取本地模型列表"""
    base_dir = Path(__file__).parent.parent.parent.parent / "basemodels"
    models = []
    if base_dir.exists():
        models = sorted([f.name for f in base_dir.glob("*.pt")])
    if not models:
        models = ["yolov8n.pt", "yolov8s.pt", "yolov8m.pt", "yolov8l.pt", "yolov8x.pt"]
    return models
