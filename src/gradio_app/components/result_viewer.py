"""
训练结果查看器组件
P2 升级：历史 run 选择器 + best.pt 下载 + 格式导出 + ModelRegistry 版本列表
"""

from pathlib import Path

import gradio as gr

from src.gradio_app.services.training_service import TrainingService

EXPORT_FORMATS = ["onnx", "torchscript", "openvino", "engine", "coreml", "tflite", "saved_model", "pb", "tfjs", "paddle", "ncnn"]


def build_result_viewer(training_svc: TrainingService):
    """构建训练结果Tab"""

    # run 选择器
    with gr.Row():
        run_dropdown = gr.Dropdown(
            choices=training_svc.list_runs(),
            value=None,
            label="训练 run（默认最新）",
            interactive=True,
            scale=3,
        )
        refresh_result_btn = gr.Button("刷新结果", variant="secondary", scale=1)

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
            scale=3,
        )
        download_btn = gr.DownloadButton(
            "下载 best.pt",
            variant="primary",
            visible=False,
            scale=1,
        )

    # 导出
    with gr.Accordion("导出模型", open=False):
        with gr.Row():
            export_format_dropdown = gr.Dropdown(
                choices=EXPORT_FORMATS,
                value="onnx",
                label="导出格式",
                scale=2,
            )
            export_btn = gr.Button("开始导出", variant="secondary", scale=1)
        export_result_md = gr.Markdown("")

    # ModelRegistry 版本
    with gr.Accordion("ModelRegistry 版本记录", open=False):
        registry_md = gr.Markdown("暂无注册版本")

    # 结果输出组件（供训练完成联动复用）
    result_outputs = [
        final_map50, final_map95, final_epoch, final_model,
        result_gallery, model_path_text,
    ]

    # --- 事件处理 ---

    def _best_weights_path(run_name: str | None):
        runs_dir = training_svc.runs_dir
        if run_name:
            candidate = runs_dir / run_name / "weights" / "best.pt"
            return candidate if candidate.exists() else None
        results = training_svc.get_training_results()
        if results.get("has_weights"):
            return Path(results["run_path"]) / "weights" / "best.pt"
        return None

    def on_refresh(run_name):
        results = training_svc.get_training_results(run_name or None)
        if "error" in results:
            return (
                gr.update(),  # run_dropdown 保持
                _metric_card("mAP@50", "--", "green"),
                _metric_card("mAP@50-95", "--", "green"),
                _metric_card("Best Epoch", "--", "amber"),
                _metric_card("模型大小", "--", "blue"),
                [],
                "尚未完成训练",
                gr.update(visible=False),
                _registry_markdown(training_svc, run_name),
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

        # 模型大小 + 下载按钮
        weights = _best_weights_path(results.get("run_name"))
        model_size = "--"
        download_update = gr.update(visible=False)
        if weights:
            model_size = f"{weights.stat().st_size / (1024 * 1024):.1f} MB"
            download_update = gr.update(visible=True, value=str(weights))

        model_path = training_svc.state.best_model_path or str(weights or "尚未完成训练")

        return (
            gr.update(choices=training_svc.list_runs()),
            _metric_card(labels[0], map50_val, "green"),
            _metric_card(labels[1] if len(labels) > 1 else "mAP@50-95", map95_val, "green"),
            _metric_card("Best Epoch", epoch_val, "amber"),
            _metric_card("模型大小", model_size, "blue"),
            results.get("result_images", []),
            model_path,
            download_update,
            _registry_markdown(training_svc, results.get("run_name")),
        )

    refresh_result_btn.click(
        fn=on_refresh,
        inputs=[run_dropdown],
        outputs=[run_dropdown, *result_outputs, download_btn, registry_md],
    )

    run_dropdown.change(
        fn=on_refresh,
        inputs=[run_dropdown],
        outputs=[run_dropdown, *result_outputs, download_btn, registry_md],
    )

    def on_export(run_name, fmt):
        weights = _best_weights_path(run_name or None)
        if not weights:
            return "未找到 best.pt，请先完成训练"
        try:
            from src.model_exporter import ModelExporter

            report = ModelExporter(str(training_svc.base_dir)).export(
                model_path=str(weights), formats=[fmt],
            )
            lines = [f"**导出 {fmt}：**"]
            for r in report.results:
                icon = "✅" if r.success else "❌"
                size = f" ({r.file_size / (1024 * 1024):.1f} MB)" if r.file_size else ""
                lines.append(f"- {icon} `{r.output_path or r.message}`{size}")
            return "\n".join(lines)
        except Exception as e:
            return f"导出失败: {e}"

    export_btn.click(
        fn=on_export,
        inputs=[run_dropdown, export_format_dropdown],
        outputs=[export_result_md],
    )

    return {
        "refresh_btn": refresh_result_btn,
        "refresh_fn": on_refresh,
        "outputs": [run_dropdown, *result_outputs, download_btn, registry_md],
    }


def _registry_markdown(training_svc: TrainingService, run_name: str | None) -> str:
    """生成选中 run 对应数据集的注册版本表"""
    dataset_name = (run_name or "").removesuffix("_auto")
    if not dataset_name:
        return "暂无注册版本"
    try:
        from src.model_registry import ModelRegistry

        versions = ModelRegistry(str(training_svc.base_dir)).get_versions(dataset_name)
    except Exception:
        return "暂无注册版本"
    if not versions:
        return "暂无注册版本"

    lines = [f"**{dataset_name}** 共 {len(versions)} 个版本：", "",
             "| 版本 | mAP@50 | 状态 | 时间 |", "|---|---|---|---|"]
    for v in sorted(versions, key=lambda x: x.created_at, reverse=True)[:10]:
        metrics = v.metrics or {}
        map50 = f"{metrics.get('mAP50', 0):.4f}" if metrics.get("mAP50") is not None else "--"
        lines.append(f"| `{v.version_id[:12]}` | {map50} | {v.status} | {v.created_at[:19]} |")
    return "\n".join(lines)


def _metric_card(label: str, value: str, color: str) -> str:
    return f'''
    <div class="metric-card">
        <div class="value {color}">{value}</div>
        <div class="label">{label}</div>
    </div>
    '''
