"""
项目级配置（阶段 B5）

基于 Pydantic Settings，集中管理所有环境变量。``AySettings`` 单例在
``get_settings()`` 中懒加载；支持从 .env 文件和环境变量读取。

使用方式：
    from src.settings import get_settings
    s = get_settings()
    s.api.api_key        # YOLO_API_KEY
    s.brand.api_title    # YOLO_API_TITLE
    s.runtime.device     # 默认 'auto'（Ultralytics 兼容字符串）

设计原则：
- 嵌套 BaseModel 表达语义分组（brand/runtime/api/storage）
- 字段类型严格（bool/int/float/list），自动转换环境变量字符串
- ``model_config = SettingsConfigDict(env_file='.env', env_nested_delimiter='_')``
  让 ``YOLO_BRAND__API_TITLE`` 这样的"嵌套"变量也能覆盖
- 提供 ``settings_dict()`` 供 CLI banner 打印
"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.__version__ import __version__


# ----------------------------------------------------------------------
# 嵌套配置
# ----------------------------------------------------------------------
class BrandSettings(BaseModel):
    """品牌展示（与 src.branding.DEFAULT_BRAND 同源，但通过 Pydantic 暴露）。"""

    name: str = "Auto YOLO Training"
    tagline: str = "通用 YOLO 模型自动训练平台 · 数据校验 / 训练 / 评估 / 导出 / 推理"
    description: str = "通用 YOLO 模型自动训练平台"
    api_title: str = "YOLO Inference API"
    api_description: str = "基于 Ultralytics 的 YOLO 模型推理服务"
    copyright: str = "Auto YOLO Training Contributors"


class RuntimeSettings(BaseModel):
    """运行时行为。"""

    # device: '' 让 Ultralytics 自动检测 GPU/CPU；也支持 'cpu' / '0' / '0,1'
    device: str = ""
    # Ultralytics 训练时的默认工作线程数
    workers: int = 8
    # 是否跳过数据校验（仅在已知数据正常时使用）
    skip_validation_default: bool = False
    # Polars CPU 检查跳过（仅在受限沙箱中使用）
    skip_polars_cpu_check: bool = False


class ApiSettings(BaseModel):
    """FastAPI 服务配置。"""

    # API Key 认证；空字符串 = 禁用认证
    api_key: str = ""
    # 是否启用 API Key 认证（当 api_key 非空时自动启用）
    require_auth: bool = False
    # 允许通过路径推理的目录白名单（逗号分隔环境变量自动转 list）
    allowed_image_dirs: list[str] = Field(default_factory=lambda: ["dataset", "test_images"])
    allowed_model_dirs: list[str] = Field(default_factory=lambda: ["runs", "basemodels"])


class StorageSettings(BaseModel):
    """存储路径覆盖。"""

    project_root: Path | None = None  # 默认 None → 走 src.constants.PROJECT_ROOT
    ultralytics_config_dir: Path = Path(".ci/ultralytics")
    matplotlib_config_dir: Path = Path(".ci/matplotlib")
    matplotlib_backend: str = "Agg"


class NotifierSettings(BaseModel):
    """通知配置。"""

    # Webhook 允许的域名白名单（逗号分隔）
    webhook_allowed_domains: str = (
        "oapi.dingtalk.com,open.feishu.cn,qyapi.weixin.qq.com,hooks.slack.com"
    )


# ----------------------------------------------------------------------
# 顶层 settings
# ----------------------------------------------------------------------
class AySettings(BaseSettings):
    """全局项目配置（单例模式由 get_settings() 实现）。

    环境变量约定（双下划线 __ 分隔嵌套层级，必须有 YOLO_ 前缀）：
        YOLO_BRAND__API_TITLE=MyFactory API     → brand.api_title
        YOLO_API__API_KEY=secret123              → api.api_key
        YOLO_RUNTIME__DEVICE=auto                → runtime.device
        YOLO_API__REQUIRE_AUTH=true              → api.require_auth

    注：变量名用双下划线是因为单下划线会被 Pydantic 当作嵌套 delimiter（``_``），
    实际要嵌套得用 ``__``（两个连续下划线）。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="YOLO_",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    # 版本（不可覆盖，仅返回）
    version: str = __version__

    # 嵌套分组
    brand: BrandSettings = Field(default_factory=BrandSettings)
    runtime: RuntimeSettings = Field(default_factory=RuntimeSettings)
    api: ApiSettings = Field(default_factory=ApiSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    notifier: NotifierSettings = Field(default_factory=NotifierSettings)

    def effective_api_auth_required(self) -> bool:
        """API Key 认证是否实际启用（api_key 非空 OR require_auth 显式开启）。"""
        return bool(self.api.api_key) or self.api.require_auth

    def settings_dict(self) -> dict:
        """以 dict 形式导出（用于 CLI banner / 调试）。"""
        return {
            "version": self.version,
            "brand.name": self.brand.name,
            "runtime.device": self.runtime.device,
            "api.auth_enabled": self.effective_api_auth_required(),
            "storage.ultralytics_config_dir": str(self.storage.ultralytics_config_dir),
        }


# ----------------------------------------------------------------------
# 单例
# ----------------------------------------------------------------------
_cached_settings: AySettings | None = None


def get_settings() -> AySettings:
    """返回全局 settings 单例（首次调用时构造）。"""
    global _cached_settings
    if _cached_settings is None:
        _cached_settings = AySettings()
    return _cached_settings


def reload_settings() -> AySettings:
    """重新加载（用于测试中改 env var 后刷新）。"""
    global _cached_settings
    _cached_settings = AySettings()
    return _cached_settings


# ----------------------------------------------------------------------
# 模块导入时的副作用：把常用 env 同步到 os.environ（向后兼容 src/__init__.py 的逻辑）
# ----------------------------------------------------------------------
def apply_runtime_env() -> None:
    """根据 settings 把相应环境变量写入 os.environ（保持旧代码兼容）。

    阶段 B6 完成后会逐步移除直接 ``os.environ.get`` 调用；现阶段为了不破坏
    已有逻辑，先在 import 期把 settings 同步到 env。
    """
    s = get_settings()
    if s.storage.ultralytics_config_dir:
        os.environ.setdefault("YOLO_CONFIG_DIR", str(s.storage.ultralytics_config_dir))
    if s.storage.matplotlib_config_dir:
        os.environ.setdefault("MPLConfig_DIR", str(s.storage.matplotlib_config_dir))
    if s.storage.matplotlib_backend:
        os.environ.setdefault("MPLBACKEND", s.storage.matplotlib_backend)
    if s.runtime.skip_polars_cpu_check:
        os.environ.setdefault("POLARS_SKIP_CPU_CHECK", "1")
    # Windows 沙箱兼容
    if "WINDIR" not in os.environ:
        _system_root = os.environ.get("SystemRoot")
        if _system_root or Path("C:/Windows").exists():
            os.environ["WINDIR"] = _system_root or "C:\\Windows"


__all__ = [
    "ApiSettings",
    "AySettings",
    "BrandSettings",
    "NotifierSettings",
    "RuntimeSettings",
    "StorageSettings",
    "apply_runtime_env",
    "get_settings",
    "reload_settings",
]
