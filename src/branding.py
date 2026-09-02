"""
项目品牌信息集中管理。

所有对外展示的标题/描述/版权都从这里读取；支持环境变量覆盖，便于企业内部
定制（例：``YOLO_API_TITLE="MyFactory Detection API" python serve.py``）。

设计原则：
- 默认值保持"通用 YOLO 训练平台"措辞，不绑定任何具体业务场景。
- 环境变量覆盖是可选的；不设置时使用默认值。
- 版本号从 :mod:`src.__version__` 注入，避免散落。
"""
from __future__ import annotations

import os

try:
    from src.__version__ import __version__
except ImportError:  # pragma: no cover - 容错，pyproject install 时 src 不在 path
    __version__ = "0.1.0"


DEFAULT_BRAND: dict[str, str] = {
    "name": "Auto YOLO Training",
    "short_name": "AYT",
    "tagline": "通用 YOLO 模型自动训练平台 · 数据校验 / 训练 / 评估 / 导出 / 推理",
    "description": "通用 YOLO 模型自动训练平台",
    "api_title": "YOLO Inference API",
    "api_description": "基于 Ultralytics 的 YOLO 模型推理服务",
    "copyright": "Auto YOLO Training Contributors",
}


# 允许通过环境变量覆盖的字段（key: 环境变量名）
ENV_OVERRIDE_KEYS: dict[str, str] = {
    "name": "YOLO_BRAND_NAME",
    "tagline": "YOLO_BRAND_TAGLINE",
    "description": "YOLO_BRAND_DESCRIPTION",
    "api_title": "YOLO_API_TITLE",
    "api_description": "YOLO_API_DESCRIPTION",
    "copyright": "YOLO_BRAND_COPYRIGHT",
}


def get_brand() -> dict[str, str]:
    """返回当前生效的品牌信息。

    返回字典包含默认值，未设置的环境变量不会覆盖。``version`` 字段单独注入。
    """
    brand = dict(DEFAULT_BRAND)
    for key, env_var in ENV_OVERRIDE_KEYS.items():
        value = os.environ.get(env_var)
        if value:
            brand[key] = value
    brand["version"] = __version__
    return brand


def get_cli_banner() -> str:
    """返回 CLI 启动 banner 字符串。"""
    brand = get_brand()
    return (
        f"{brand['name']} v{brand['version']}\n"
        f"{brand['tagline']}\n"
        f"Copyright (c) {brand['copyright']}"
    )


def get_api_metadata() -> dict[str, str]:
    """返回 FastAPI app 的元数据，可直接 ``**`` 解包到 ``FastAPI(...)``。"""
    brand = get_brand()
    return {
        "title": brand["api_title"],
        "description": brand["api_description"],
        "version": brand["version"],
    }


__all__ = [
    "DEFAULT_BRAND",
    "ENV_OVERRIDE_KEYS",
    "get_brand",
    "get_cli_banner",
    "get_api_metadata",
]