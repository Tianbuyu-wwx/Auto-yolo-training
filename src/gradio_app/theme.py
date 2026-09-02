"""
YOLO训练平台深色工业主题
Linear x Grafana 融合风格
"""

import gradio as gr


def create_theme() -> gr.themes.Base:
    """创建深色工业主题"""
    return gr.themes.Base(
        primary_hue=gr.themes.colors.blue,
        secondary_hue=gr.themes.colors.slate,
        neutral_hue=gr.themes.colors.slate,
        font=gr.themes.GoogleFont("Noto Sans SC"),
        font_mono=gr.themes.GoogleFont("JetBrains Mono"),
    ).set(
        body_background_fill="oklch(0.13 0.01 260)",
        body_background_fill_dark="oklch(0.10 0.01 260)",
        block_background_fill="oklch(0.17 0.01 260)",
        block_background_fill_dark="oklch(0.15 0.01 260)",
        block_border_color="oklch(0.25 0.01 260)",
        block_border_color_dark="oklch(0.22 0.01 260)",
        block_title_text_color="oklch(0.90 0.01 260)",
        block_title_text_color_dark="oklch(0.88 0.01 260)",
        body_text_color="oklch(0.90 0.01 260)",
        body_text_color_dark="oklch(0.88 0.01 260)",
        body_text_color_subdued="oklch(0.60 0.01 260)",
        body_text_color_subdued_dark="oklch(0.55 0.01 260)",
        input_background_fill="oklch(0.20 0.01 260)",
        input_background_fill_dark="oklch(0.18 0.01 260)",
        input_border_color="oklch(0.30 0.01 260)",
        input_border_color_dark="oklch(0.28 0.01 260)",
        button_primary_background_fill="oklch(0.55 0.19 250)",
        button_primary_background_fill_hover="oklch(0.60 0.19 250)",
        button_primary_text_color="white",
        button_secondary_background_fill="oklch(0.25 0.01 260)",
        button_secondary_background_fill_hover="oklch(0.30 0.01 260)",
        button_secondary_text_color="oklch(0.85 0.01 260)",
        button_cancel_background_fill="oklch(0.55 0.20 25)",
        button_cancel_text_color="white",
        border_color_primary="oklch(0.30 0.01 260)",
        border_color_primary_dark="oklch(0.28 0.01 260)",
        shadow_drop_lg="0 4px 20px oklch(0.05 0.02 260 / 0.4)",
    )
