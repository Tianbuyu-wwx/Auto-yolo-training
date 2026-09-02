"""
训练监控面板组件
含实时指标卡片 + 训练曲线 + 日志
"""

import gradio as gr
from typing import Dict, Any

from src.gradio_app.services.training_service import TrainingService
from src.gradio_app.services.log_service import LogService
from src.gradio_app.models.training_state import TrainingConfig


def build_training_monitor(training_svc: TrainingService, log_svc: LogService):
    """构建训练监控Tab"""

    # 状态指示
    with gr.Row():
        status_html = gr.HTML(
            value='<div class="status-indicator"><span class="status-dot idle"></span>idle</div>',
            label="状态",
        )
        with gr.Row():
            start_btn = gr.Button("开始训练", variant="primary", size="lg")
            stop_btn = gr.Button("停止训练", variant="stop", size="lg", interactive=False)

    # 指标卡片
    with gr.Row():
        epoch_card = gr.HTML(
            value=_metric_card("Epoch", "0 / 0", "amber"),
            elem_classes=["metric-card"],
        )
        loss_card = gr.HTML(
            value=_metric_card("Loss", "0.0000", "blue"),
            elem_classes=["metric-card"],
        )
        map50_card = gr.HTML(
            value=_metric_card("mAP@50", "0.0000", "green"),
            elem_classes=["metric-card"],
        )
        map95_card = gr.HTML(
            value=_metric_card("mAP@50-95", "0.0000", "green"),
            elem_classes=["metric-card"],
        )

    # 训练曲线
    with gr.Row():
        loss_plot = gr.LinePlot(
            x="epoch", y="loss",
            title="训练损失",
            x_title="Epoch", y_title="Loss",
            height=280,
        )
        map_plot = gr.LinePlot(
            x="epoch", y="mAP",
            title="mAP 指标",
            x_title="Epoch", y_title="mAP",
            height=280,
        )

    # 训练日志
    log_output = gr.Textbox(
        value="",
        label="训练日志",
        lines=15,
        max_lines=50,
        autoscroll=True,
        elem_classes=["training-log"],
        interactive=False,
    )

    # --- 定时更新 ---

    def update_status():
        status = training_svc.get_status()

        # 状态指示器
        if status["is_running"]:
            if status["is_stopping"]:
                dot_class = "running"
                status_text = "正在停止..."
            else:
                dot_class = "running"
                status_text = f"训练中 [{status['current_stage']}]"
        elif status["success"]:
            dot_class = "success"
            status_text = "训练完成"
        elif status["error_message"]:
            dot_class = "error"
            status_text = f"失败: {status['error_message'][:50]}"
        else:
            dot_class = "idle"
            status_text = "idle"

        status_html_val = f'<div class="status-indicator"><span class="status-dot {dot_class}"></span>{status_text}</div>'

        # 指标卡片
        epoch_val = _metric_card("Epoch", f'{status["current_epoch"]} / {status["total_epochs"]}', "amber")
        loss_val = _metric_card("Loss", f'{status["current_loss"]:.4f}', "blue")
        map50_val = _metric_card("mAP@50", f'{status["current_map50"]:.4f}', "green")
        map95_val = _metric_card("mAP@50-95", f'{status["current_map50_95"]:.4f}', "green")

        # 按钮状态
        start_interactive = not status["is_running"]
        stop_interactive = status["is_running"] and not status["is_stopping"]

        # 曲线数据
        loss_data = training_svc.state.loss_history if training_svc.state.loss_history else None
        map_data = training_svc.state.map_history if training_svc.state.map_history else None

        return (
            status_html_val,
            epoch_val, loss_val, map50_val, map95_val,
            gr.update(interactive=start_interactive),
            gr.update(interactive=stop_interactive),
            gr.update(value=loss_data),
            gr.update(value=map_data),
            status["logs"],
        )

    timer = gr.Timer(value=2, active=True)
    timer.tick(
        fn=update_status,
        outputs=[
            status_html,
            epoch_card, loss_card, map50_card, map95_card,
            start_btn, stop_btn,
            loss_plot, map_plot,
            log_output,
        ],
    )

    return {
        "start_btn": start_btn,
        "stop_btn": stop_btn,
        "timer": timer,
    }


def _metric_card(label: str, value: str, color: str) -> str:
    """生成指标卡片HTML"""
    return f'''
    <div class="metric-card">
        <div class="value {color}">{value}</div>
        <div class="label">{label}</div>
    </div>
    '''
