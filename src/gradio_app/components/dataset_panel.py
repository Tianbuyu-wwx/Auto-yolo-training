"""
数据集管理面板组件
使用全局 dataset_dropdown，避免与顶部选择器重复
"""

import gradio as gr
from typing import Dict, Any

from src.gradio_app.services.dataset_service import DatasetService


def build_dataset_panel(dataset_svc: DatasetService, dataset_dropdown: gr.Dropdown):
    """构建数据集管理Tab

    Args:
        dataset_svc: 数据集服务
        dataset_dropdown: 顶部全局数据集选择器（传入后与本Tab联动）
    """

    with gr.Row():
        # 左侧：上传与操作
        with gr.Column(scale=1, min_width=280):
            gr.Markdown("### 上传")
            upload_file = gr.File(
                label="上传数据集 (ZIP)",
                file_types=[".zip"],
            )
            upload_name = gr.Textbox(
                label="数据集名称（可选）",
                placeholder="留空使用文件名",
                max_lines=1,
            )
            upload_btn = gr.Button("上传并解压", variant="secondary")

            gr.Markdown("---")
            refresh_btn = gr.Button("刷新数据集列表", size="sm")

        # 右侧：数据集详情
        with gr.Column(scale=2):
            dataset_info = gr.Markdown(
                "请在顶部选择数据集",
                elem_classes=["dataset-detail"],
            )
            sample_gallery = gr.Gallery(
                label="样本预览",
                columns=4,
                rows=1,
                height=160,
                value=[],
                interactive=False,
                elem_classes=["hide-gallery-upload"],
            )
            validate_btn = gr.Button("验证数据集", variant="primary")
            validate_result = gr.Markdown(visible=False)

    # --- 事件处理 ---

    def on_refresh():
        datasets = dataset_svc.list_datasets()
        choices = ["-- 请选择 --"] + datasets
        return gr.update(choices=choices, value=choices[0])

    def on_dataset_selected(dataset_name: str):
        if not dataset_name or dataset_name.startswith("--"):
            return "请在顶部选择数据集", [], gr.update(visible=False)
        info = dataset_svc.get_info(dataset_name)
        if "error" in info:
            return info["error"], [], gr.update(visible=False)

        splits = info.get("splits", {})
        md = f"### {info['name']}\n\n"
        md += "| 划分 | 图像数 | 标注数 |\n|------|--------|--------|\n"
        for split in ["train", "val", "test"]:
            s = splits.get(split, {})
            md += f"| {split} | {s.get('images', 0)} | {s.get('labels', 0)} |\n"
        md += f"\n**总计**: {info.get('total_images', 0)} 张图像"

        samples = info.get("sample_images", [])
        return md, samples, gr.update(visible=False)

    def on_upload(file_obj, name: str):
        if file_obj is None:
            return "请先选择文件", "-- 请选择 --", "请在顶部选择数据集"
        result = dataset_svc.extract(file_obj, name or None)
        if result["status"] == "success":
            datasets = dataset_svc.list_datasets()
            choices = ["-- 请选择 --"] + datasets
            new_value = result.get("dataset_name", choices[0])
            # 上传后自动选中该数据集
            md, samples, _ = on_dataset_selected(new_value)
            return md, gr.update(choices=choices, value=new_value), md
        return result["message"], "-- 请选择 --", result["message"]

    def on_validate(dataset_name: str):
        if not dataset_name or dataset_name.startswith("--"):
            return gr.update(value="请在顶部选择数据集", visible=True)
        result = dataset_svc.validate(dataset_name)
        return gr.update(value=result.get("message", ""), visible=True)

    # 刷新按钮：更新全局 dataset_dropdown
    refresh_btn.click(fn=on_refresh, outputs=[dataset_dropdown])

    # 全局 dataset_dropdown 切换：刷新详情
    dataset_dropdown.change(
        fn=on_dataset_selected,
        inputs=[dataset_dropdown],
        outputs=[dataset_info, sample_gallery, validate_result],
    )

    # 上传：更新全局选择器 + 详情
    upload_btn.click(
        fn=on_upload,
        inputs=[upload_file, upload_name],
        outputs=[dataset_info, dataset_dropdown, validate_result],
    )

    # 验证
    validate_btn.click(
        fn=on_validate,
        inputs=[dataset_dropdown],
        outputs=[validate_result],
    )

    return {
        "info": dataset_info,
        "gallery": sample_gallery,
        "validate_result": validate_result,
    }
