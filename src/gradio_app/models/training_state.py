"""
训练状态与配置数据模型
"""

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TrainingState:
    """训练状态（线程安全）"""
    is_running: bool = False
    is_stopping: bool = False
    current_stage: str = ""
    current_epoch: int = 0
    total_epochs: int = 0
    current_loss: float = 0.0
    current_map50: float = 0.0
    current_map50_95: float = 0.0
    log_messages: list[str] = field(default_factory=list)
    start_time: str | None = None
    end_time: str | None = None
    error_message: str | None = None
    success: bool = False
    best_model_path: str | None = None

    # 训练曲线数据
    loss_history: list[dict[str, Any]] = field(default_factory=list)
    map_history: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        self._lock = threading.Lock()

    def update(self, **kwargs):
        """线程安全地更新状态"""
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self, key):
                    setattr(self, key, value)

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "is_running": self.is_running,
                "is_stopping": self.is_stopping,
                "current_stage": self.current_stage,
                "current_epoch": self.current_epoch,
                "total_epochs": self.total_epochs,
                "current_loss": self.current_loss,
                "current_map50": self.current_map50,
                "current_map50_95": self.current_map50_95,
                "start_time": self.start_time,
                "end_time": self.end_time,
                "error_message": self.error_message,
                "success": self.success,
                "best_model_path": self.best_model_path,
                "progress": self._calculate_progress(),
            }

    def _calculate_progress(self) -> float:
        if not self.is_running:
            return 100.0 if self.success else 0.0
        if self.total_epochs == 0:
            return 0.0
        return min(self.current_epoch / self.total_epochs * 100, 99.0)


@dataclass
class TrainingConfig:
    """训练配置（替代15个参数的函数签名）"""
    dataset_name: str = ""
    model: str = "yolov8s.pt"
    epochs: int = 150
    imgsz: int = 640
    batch: int = 16
    device: str = ""  # 通用化默认：空字符串让 Ultralytics 自动检测 GPU/CPU（不接受 "auto"）
    workers: int = 8
    lr0: float = 0.001
    optimizer: str = "AdamW"
    cos_lr: bool = True
    lrf: float = 0.01
    warmup_epochs: float = 3.0
    patience: int = 30
    dropout: float = 0.0
    mosaic: float = 1.0
    mixup: float = 0.0
    degrees: float = 0.0
    scale: float = 0.5
    # 新增高级参数
    cache: Any = "disk"
    rect: bool = True
    deterministic: bool = False
    freeze: int = 0
    label_smoothing: float = 0.0
    weight_decay: float = 0.0005
    box: float = 7.5
    cls: float = 0.5
    dfl: float = 1.5
    copy_paste: float = 0.0
    close_mosaic: int = 10
    translate: float = 0.1
    shear: float = 0.0
    perspective: float = 0.0
    flipud: float = 0.0
    hsv_h: float = 0.015
    hsv_s: float = 0.7
    hsv_v: float = 0.4
    skip_validation: bool = False

    def to_overrides(self) -> dict[str, Any]:
        """转换为 TrainingPipeline 的 overrides 字典"""
        return {
            "lr0": self.lr0,
            "optimizer": self.optimizer,
            "cos_lr": self.cos_lr,
            "lrf": self.lrf,
            "warmup_epochs": self.warmup_epochs,
            "patience": self.patience,
            "dropout": self.dropout,
            "mosaic": self.mosaic,
            "mixup": self.mixup,
            "degrees": self.degrees,
            "scale": self.scale,
            "translate": self.translate,
            "shear": self.shear,
            "perspective": self.perspective,
            "flipud": self.flipud,
            "hsv_h": self.hsv_h,
            "hsv_s": self.hsv_s,
            "hsv_v": self.hsv_v,
            "cache": self.cache,
            "rect": self.rect,
            "deterministic": self.deterministic,
            "freeze": self.freeze,
            "label_smoothing": self.label_smoothing,
            "weight_decay": self.weight_decay,
            "box": self.box,
            "cls": self.cls,
            "dfl": self.dfl,
            "copy_paste": self.copy_paste,
            "close_mosaic": self.close_mosaic,
            "device": self.device,
            "workers": self.workers,
        }


# 参数预设
PRESETS = {
    "快速验证": {
        "epochs": 50, "batch": 16, "imgsz": 416,
        "patience": 10, "lr0": 0.002,
    },
    "标准训练": {
        "epochs": 150, "batch": 16, "imgsz": 640,
        "patience": 30, "lr0": 0.001,
    },
    "精细调优": {
        "epochs": 300, "batch": 8, "imgsz": 640,
        "patience": 50, "lr0": 0.0005,
    },
}
