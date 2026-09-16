"""
Gradio前端界面模块
提供YOLO模型自动训练的可视化Web界面

注意：此处**不得**在模块顶层 `from .app import ...`。

`.app` 会 `import gradio`，而本包下的 models/services 子模块被大量非 Gradio
代码路径间接依赖（`src/api/admin.py` 引 TrainingConfig / DatasetService /
TrainingService，多个 CLI 入口同理）。顶层 eager import 会把这些路径全部
绑死在 gradio 这一重量级依赖上——实测：未安装 gradio 的干净环境中
`ayt-web` 直接 ModuleNotFoundError: gradio 而无法启动。

因此改为 PEP 562 惰性导出：
- `from src.gradio_app import create_app` 仍然可用（首次属性访问时才加载 .app）
- `from src.gradio_app.services.xxx import Yyy` 不再连带拉入 gradio
"""

from typing import Any

__all__ = ["create_app", "main"]


def __getattr__(name: str) -> Any:
    """PEP 562 模块级惰性属性，仅在真正访问导出名时才加载 Gradio 应用。"""
    if name in __all__:
        from . import app as _app

        return getattr(_app, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)
