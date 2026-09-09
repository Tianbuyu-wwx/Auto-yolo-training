"""
训练监控面板组件
含实时指标卡片 + 进度条/ETA + 训练曲线 + 日志 + 错误详情
"""

import contextlib

import gradio as gr

from src.gradio_app.services.log_service import LogService
from src.gradio_app.services.training_service import TrainingService

# 状态签名：用于空闲时跳过重量级输出刷新（避免每 2s 全量重渲染）
_SIGNATURE_KEYS = ("is_running", "is_stopping", "current_epoch",
                   "success", "error_message", "current_loss",
                   "current_map50", "current_map50_95", "eta_seconds")


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
            queue_btn = gr.Button("加入队列", variant="secondary", size="lg")

    queue_status_md = gr.Markdown(visible=False)

    # 进度条（含 ETA）
    progress_html = gr.HTML(
        value=_progress_bar(0.0, None),
        elem_classes=["training-progress"],
    )

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

    # 断点续训（P2-4）
    with gr.Accordion("断点续训", open=False):
        with gr.Row():
            resume_checkbox = gr.Checkbox(
                value=False,
                label="从 checkpoint 恢复训练",
                info="使用所选 last.pt 继续，超参数以 checkpoint 保存值为准",
            )
            refresh_ckpt_btn = gr.Button("刷新 checkpoint 列表", size="sm")
        resume_dropdown = gr.Dropdown(
            choices=training_svc.list_checkpoints(),
            value=None,
            label="checkpoint (last.pt)",
            interactive=True,
        )

    refresh_ckpt_btn.click(
        fn=lambda: gr.update(choices=training_svc.list_checkpoints()),
        outputs=[resume_dropdown],
    )

    # 错误详情（完整堆栈/消息，不截断）
    with gr.Accordion("错误详情", open=False, visible=False) as error_accordion:
        error_detail_md = gr.Markdown("")

    # 完成信号：训练结束时非 None，供 app.py 联动刷新结果页
    finished_signal = gr.State(None)

    # --- 定时更新 ---

    def update_status():
        status = training_svc.get_status()
        prev = training_svc.last_rendered_signature

        signature = tuple(status.get(k) for k in _SIGNATURE_KEYS)
        training_svc.last_rendered_signature = signature
        unchanged = signature == prev

        # 状态指示器
        if status["is_running"]:
            dot_class = "running"
            if status["is_stopping"]:
                status_text = "正在停止..."
            else:
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

        # 指标卡片（标签跟随任务变化：detect→mAP@50，classify→Accuracy@1）
        labels = status.get("metric_labels") or ["mAP@50", "mAP@50-95"]
        epoch_val = _metric_card("Epoch", f'{status["current_epoch"]} / {status["total_epochs"]}', "amber")
        loss_val = _metric_card("Loss", f'{status["current_loss"]:.4f}', "blue")
        map50_val = _metric_card(labels[0], f'{status["current_map50"]:.4f}', "green")
        map95_val = _metric_card(labels[1], f'{status["current_map50_95"]:.4f}', "green")

        # 进度条 + ETA
        progress_val = _progress_bar(status.get("progress", 0.0), status.get("eta_seconds"))

        # 按钮状态
        start_interactive = not status["is_running"]
        stop_interactive = status["is_running"] and not status["is_stopping"]

        # 完成过渡检测：上一轮在跑、这一轮结束 → 通知 + 结果页联动 + 错误详情
        finished = None
        just_ended = prev is not None and _was_running(prev) and not status["is_running"]
        if just_ended:
            if status["success"]:
                finished = {"success": True}
                with contextlib.suppress(Exception):
                    gr.Info("训练完成 ✅ 结果见「④ 结果」页")
            elif status["error_message"]:
                finished = {"success": False}
                with contextlib.suppress(Exception):
                    gr.Warning("训练失败，详见错误详情")

        error_detail = gr.update()
        error_accordion_state = gr.update()
        if just_ended and not status["success"] and status["error_message"]:
            error_detail = gr.update(value=status["error_message"])
            error_accordion_state = gr.update(visible=True)
        elif prev is not None and not _was_running(prev) and not status["is_running"] and not status["error_message"]:
            # 非错误状态保持折叠
            error_accordion_state = gr.update(visible=False)

        # 曲线数据（仅运行中或刚有变化时刷新）
        if unchanged and not just_ended:
            plots = gr.update(), gr.update()
        else:
            loss_data = training_svc.state.loss_history or None
            map_data = training_svc.state.map_history or None
            plots = gr.update(value=loss_data), gr.update(value=map_data)

        # 日志：运行中每 tick 刷新；空闲时只在状态变化时刷新一次
        if status["is_running"] or not unchanged or just_ended:
            logs = status["logs"]
        else:
            logs = gr.update()

        return (
            status_html_val,
            epoch_val, loss_val, map50_val, map95_val,
            progress_val,
            gr.update(interactive=start_interactive),
            gr.update(interactive=stop_interactive),
            *plots,
            logs,
            error_detail,
            error_accordion_state,
            finished,
        )

    timer = gr.Timer(value=2, active=True)
    tick_event = timer.tick(
        fn=update_status,
        outputs=[
            status_html,
            epoch_card, loss_card, map50_card, map95_card,
            progress_html,
            start_btn, stop_btn,
            loss_plot, map_plot,
            log_output,
            error_detail_md,
            error_accordion,
            finished_signal,
        ],
    )

    return {
        "start_btn": start_btn,
        "stop_btn": stop_btn,
        "queue_btn": queue_btn,
        "queue_status_md": queue_status_md,
        "timer": timer,
        "tick_event": tick_event,
        "finished_signal": finished_signal,
        "resume_checkbox": resume_checkbox,
        "resume_dropdown": resume_dropdown,
    }


def _was_running(prev_signature: tuple) -> bool:
    """从上一轮签名恢复 is_running 字段"""
    try:
        idx = _SIGNATURE_KEYS.index("is_running")
        return bool(prev_signature[idx])
    except (ValueError, IndexError):
        return False


def _format_eta(seconds: float | None) -> str:
    if seconds is None:
        return ""
    seconds = int(seconds)
    if seconds <= 0:
        return "即将完成"
    if seconds < 60:
        return f"预计剩余 {seconds} 秒"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"预计剩余 {minutes} 分 {sec:02d} 秒"
    hours, minutes = divmod(minutes, 60)
    return f"预计剩余 {hours} 时 {minutes:02d} 分"


def _progress_bar(progress: float, eta_seconds: float | None) -> str:
    """生成进度条 HTML（样式复用 styles.css 的 .progress-bar-*）"""
    pct = max(0.0, min(100.0, float(progress or 0.0)))
    eta_text = _format_eta(eta_seconds)
    eta_html = f'<span class="progress-eta">{eta_text}</span>' if eta_text else ""
    return f'''
    <div class="progress-wrapper">
        <div class="progress-bar-container"><div class="progress-bar-fill" style="width: {pct:.1f}%"></div></div>
        <div class="progress-meta"><span>{pct:.1f}%</span>{eta_html}</div>
    </div>
    '''


def _metric_card(label: str, value: str, color: str) -> str:
    """生成指标卡片HTML"""
    return f'''
    <div class="metric-card">
        <div class="value {color}">{value}</div>
        <div class="label">{label}</div>
    </div>
    '''
