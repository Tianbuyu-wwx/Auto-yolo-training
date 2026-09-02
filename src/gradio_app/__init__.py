"""
Gradio前端界面模块
提供YOLO模型自动训练的可视化Web界面
"""

from .app import create_app, main

__all__ = ["create_app", "main"]
