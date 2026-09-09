"""
训练结果查看器组件
"""


import gradio as gr

from src.gradio_app.services.training_service import TrainingService


def build_result_viewer(training_svc: TrainingService):
    """构建训练结果Tab"""

    # 最终指标
    with gr.Row():
        final_map50 = gr.HTML(
            value=_metric_card("mAP@50", "--", "green"),
            elem_classes=["metric-card"],
        )
        final_map95 = gr.HTML(
            value=_metric_card("mAP@50-95", "--", "green"),
            elem_classes=["metric-card"],
        )
        final_epoch = gr.HTML(
            value=_metric_card("Best Epoch", "--", "amber"),
            elem_classes=["metric-card"],
        )
        final_model = gr.HTML(
            value=_metric_card("模型大小", "--", "blue"),
            elem_classes=["metric-card"],
        )

    # 结果图表
    gr.Markdown("### 结果图表")
    result_gallery = gr.Gallery(
        label="",
        columns=3,
        rows=2,
        height=360,
        value=[],
        interactive=False,
        elem_classes=["hide-gallery-upload"],
    )

    # 模型操作
    gr.Markdown("### 模型操作")
    with gr.Row():
        model_path_text = gr.Textbox(
            value="尚未完成训练",
            label="最佳模型路径",
            interactive=False,
        )
    with gr.Row():
        refresh_result_btn = gr.Button("刷新结果", variant="secondary")

    # 结果输出组件（供训练完成联动复用）
    result_outputs = [
        final_map50, final_map95, final_epoch, final_model,
        result_gallery, model_path_text,
    ]

    # --- 事件处理 ---

    def on_refresh():
        results = training_svc.get_training_results()
        if "error" in results:
            return (
                _metric_card("mAP@50", "--", "green"),
                _metric_card("mAP@50-95", "--", "green"),
                _metric_card("Best Epoch", "--", "amber"),
                _metric_card("模型大小", "--", "blue"),
                [],
                "尚未完成训练",
            )

        metrics = results.get("final_metrics", {})
        # 标签跟随任务（detect→mAP@50，classify→Accuracy@1 等）
        labels = results.get("metric_labels") or ["mAP@50", "mAP@50-95"]
        primary = metrics.get("primary", {}) if metrics else {}
        map50_val = f"{primary.get(labels[0], metrics.get('mAP50', 0)):.4f}" if metrics else "--"
        map95_val = (
            f"{primary.get(labels[1], metrics.get('mAP50_95', 0)):.4f}"
            if metrics and len(labels) > 1 else "--"
        )
        epoch_val = str(metrics.get("epoch", "--")) if metrics else "--"

        # 模型大小
        model_path = training_svc.state.best_model_path
        model_size = "--"
        if model_path:
            from pathlib import Path
            p = Path(model_path)
            if p.exists():
                model_size = f"{p.stat().st_size / (1024*1024):.1f} MB"

        return (
            _metric_card(labels[0], map50_val, "green"),
            _metric_card(labels[1], map95_val, "green"),
            _metric_card("Best Epoch", epoch_val, "amber"),
            _metric_card("模型大小", model_size, "blue"),
            results.get("result_images", []),
            model_path or "尚未完成训练",
        )

    refresh_result_btn.click(
        fn=on_refresh,
        outputs=result_outputs,
    )

    return {
        "refresh_btn": refresh_result_btn,
        "refresh_fn": on_refresh,
        "outputs": result_outputs,
    }


def _metric_card(label: str, value: str, color: str) -> str:
    return f'''
    <div class="metric-card">
        <div class="value {color}">{value}</div>
        <div class="label">{label}</div>
    </div>
    '''
