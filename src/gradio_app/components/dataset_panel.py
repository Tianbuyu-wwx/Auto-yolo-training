"""
数据集管理面板组件
使用全局 dataset_dropdown，避免与顶部选择器重复
"""


import gradio as gr

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
            upload_overwrite = gr.Checkbox(
                value=False,
                label="覆盖同名数据集",
                info="不勾选时，同名数据集已存在将拒绝上传（防误删）",
            )
            upload_btn = gr.Button("上传并解压", variant="secondary")

            gr.Markdown("---")
            gr.Markdown("### 格式转换")
            convert_status_md = gr.Markdown("", elem_classes=["convert-status"])
            convert_delete_original = gr.Checkbox(
                value=False,
                label="转换后删除原始数据集",
                info="默认保留原始数据集；转换结果写入「<名称>-yolo」",
            )
            convert_btn = gr.Button("转换为 YOLO 格式", variant="secondary", size="sm")
            convert_result_md = gr.Markdown(visible=False)

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
        return (
            gr.update(choices=choices, value=choices[0]),
            _pending_conversion_markdown(),
        )

    def _pending_conversion_markdown() -> str:
        pending = dataset_svc.get_pending_conversion()
        if not pending:
            return "✅ 所有数据集均为 YOLO 格式"
        return (
            f"⚠️ **{len(pending)} 个数据集为分类格式，可转换：** "
            + "、".join(f"`{n}`" for n in pending)
        )

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

    def on_upload(file_obj, name: str, overwrite: bool):
        if file_obj is None:
            return "请先选择文件", "-- 请选择 --", "请在顶部选择数据集", gr.update(visible=False)
        result = dataset_svc.extract(file_obj, name or None, overwrite=overwrite)
        if result["status"] == "success":
            datasets = dataset_svc.list_datasets()
            choices = ["-- 请选择 --"] + datasets
            new_value = result.get("dataset_name", choices[0])
            # 上传后自动选中该数据集
            md, samples, _ = on_dataset_selected(new_value)
            return md, gr.update(choices=choices, value=new_value), md, _pending_conversion_markdown()
        if result["status"] == "exists":
            # 同名冲突：不改动当前选择，提示用户勾选覆盖
            return result["message"], gr.update(), result["message"], gr.update(visible=False)
        return result["message"], "-- 请选择 --", result["message"], gr.update(visible=False)

    def on_validate(dataset_name: str):
        if not dataset_name or dataset_name.startswith("--"):
            return gr.update(value="请在顶部选择数据集", visible=True)
        result = dataset_svc.validate(dataset_name)
        return gr.update(value=result.get("message", ""), visible=True)

    def on_convert(dataset_name: str, delete_original: bool):
        if not dataset_name or dataset_name.startswith("--"):
            return gr.update(value="请在顶部选择数据集", visible=True)
        result = dataset_svc.convert(dataset_name, delete_original=delete_original)
        msg = result.get("message", "")
        return gr.update(value=msg, visible=True)

    # 刷新按钮：更新全局 dataset_dropdown
    refresh_btn.click(
        fn=on_refresh,
        outputs=[dataset_dropdown, convert_status_md],
    )

    # 全局 dataset_dropdown 切换：刷新详情
    dataset_dropdown.change(
        fn=on_dataset_selected,
        inputs=[dataset_dropdown],
        outputs=[dataset_info, sample_gallery, validate_result],
    )

    # 上传：更新全局选择器 + 详情
    upload_btn.click(
        fn=on_upload,
        inputs=[upload_file, upload_name, upload_overwrite],
        outputs=[dataset_info, dataset_dropdown, validate_result, convert_status_md],
    )

    # 验证
    validate_btn.click(
        fn=on_validate,
        inputs=[dataset_dropdown],
        outputs=[validate_result],
    )

    # 分类 → YOLO 转换（显式触发）
    convert_btn.click(
        fn=on_convert,
        inputs=[dataset_dropdown, convert_delete_original],
        outputs=[convert_result_md],
    )

    return {
        "info": dataset_info,
        "gallery": sample_gallery,
        "validate_result": validate_result,
        "convert_status": convert_status_md,
    }
