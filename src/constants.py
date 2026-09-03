"""
项目常量与配置
统一管理所有硬编码路径和默认值
"""

# 项目根目录（默认为 src 的父目录，可通过环境变量覆盖）
import os
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get("YOLO_PROJECT_ROOT", Path(__file__).parent.parent))

# 目录结构
DATASET_DIR = PROJECT_ROOT / "dataset"
RUNS_DIR = PROJECT_ROOT / "runs" / "detect"
BASEMODELS_DIR = PROJECT_ROOT / "basemodels"
CONFIGS_DIR = PROJECT_ROOT / "configs"
MODELS_CONFIG_DIR = CONFIGS_DIR / "models"
TRAIN_CONFIG_DIR = CONFIGS_DIR / "train"
REPORTS_DIR = PROJECT_ROOT / "reports"
LOGS_DIR = PROJECT_ROOT / "logs"

# 支持的图像格式
SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}

# 路径白名单（相对项目根目录）
ALLOWED_IMAGE_DIRS = ["dataset", "test_images"]
ALLOWED_MODEL_DIRS = ["runs", "basemodels"]

# 训练默认参数
DEFAULT_MODEL = "yolov8s.pt"
DEFAULT_IMGSZ = 640
DEFAULT_BATCH = 16
DEFAULT_EPOCHS = 150

# 服务默认配置
DEFAULT_HOST = "127.0.0.1"
DEFAULT_API_PORT = 8000
DEFAULT_GRADIO_PORT = 7860


class ProjectPaths:
    """基于任意项目根目录的路径工具类"""

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)

    @property
    def dataset_dir(self) -> Path:
        return self.base_dir / "dataset"

    @property
    def runs_dir(self) -> Path:
        return self.base_dir / "runs" / "detect"

    @property
    def basemodels_dir(self) -> Path:
        return self.base_dir / "basemodels"

    @property
    def exports_dir(self) -> Path:
        return self.base_dir / "exports"

    @property
    def reports_dir(self) -> Path:
        return self.base_dir / "reports"

    @property
    def logs_dir(self) -> Path:
        return self.base_dir / "logs"
