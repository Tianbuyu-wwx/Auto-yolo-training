"""
配置自动生成模块
根据数据集自动生成YOLO训练所需的data.yaml和训练配置
"""

import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from src.utils import resolve_model_path

logger = logging.getLogger(__name__)


class ClassInferenceError(Exception):
    """无法从数据集推断类别时抛出的明确错误。

    设计变更（2026-09-02）：原实现静默回退到硬编码业务名（``["break", "thunderbolt"]``），
    违反项目通用化目标。改为抛出此异常，让调用方显式提供类别名。
    """

    def __init__(self, dataset_path: Path, message: str):
        self.dataset_path = Path(dataset_path)
        super().__init__(message)


@dataclass
class DatasetConfig:
    """数据集配置"""
    path: str
    train: str
    val: str
    test: str | None = None
    nc: int = 0
    names: list[str] = field(default_factory=list)

    def to_yaml(self) -> str:
        data = {}
        if self.path:
            data["path"] = self.path
        data["train"] = self.train
        data["val"] = self.val
        if self.test:
            data["test"] = self.test
        data["nc"] = self.nc
        data["names"] = self.names
        return yaml.dump(data, sort_keys=False, allow_unicode=True)


@dataclass
class TrainingConfig:
    """训练超参数配置"""
    task: str = "detect"  # 阶段 C2：Ultralytics 任务类型（detect/segment/pose/classify/obb）
    model: str = "yolov8s.pt"
    epochs: int = 150
    imgsz: int = 640
    batch: int = 16
    workers: int = 8
    device: str = "0"
    patience: int = 30
    save: bool = True
    save_period: int = 10
    cache: Any = "disk"
    exist_ok: bool = False
    pretrained: bool = True
    optimizer: str = "AdamW"
    verbose: bool = True
    seed: int = 0
    deterministic: bool = False
    single_cls: bool = False
    rect: bool = True
    cos_lr: bool = True
    close_mosaic: int = 10
    resume: bool = False
    amp: bool = True
    fraction: float = 1.0
    profile: bool = False
    freeze: int | None = None
    lr0: float = 0.001
    lrf: float = 0.01
    momentum: float = 0.937
    weight_decay: float = 0.0005
    warmup_epochs: float = 3.0
    warmup_momentum: float = 0.8
    warmup_bias_lr: float = 0.1
    box: float = 7.5
    cls: float = 0.5
    dfl: float = 1.5
    pose: float = 12.0
    kobj: float = 1.0
    label_smoothing: float = 0.0
    nbs: int = 64
    overlap_mask: bool = True
    mask_ratio: int = 4
    dropout: float = 0.0
    val: bool = True
    plots: bool = True

    # 数据增强参数
    hsv_h: float = 0.015
    hsv_s: float = 0.7
    hsv_v: float = 0.4
    degrees: float = 0.0
    translate: float = 0.1
    scale: float = 0.5
    shear: float = 0.0
    perspective: float = 0.0
    flipud: float = 0.0
    fliplr: float = 0.5
    bgr: float = 0.0
    mosaic: float = 1.0
    mixup: float = 0.0
    copy_paste: float = 0.0
    copy_paste_mode: str = "flip"
    auto_augment: str = "randaugment"
    erasing: float = 0.4
    crop_fraction: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class ProjectConfig:
    """项目级配置"""
    project_name: str
    dataset_name: str
    dataset_path: str
    output_dir: str
    data_yaml_path: str
    training_config: TrainingConfig
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_name": self.project_name,
            "dataset_name": self.dataset_name,
            "dataset_path": self.dataset_path,
            "output_dir": self.output_dir,
            "data_yaml_path": self.data_yaml_path,
            "training_config": self.training_config.to_dict(),
            "created_at": self.created_at,
            "description": self.description,
        }


class ConfigGenerator:
    """配置生成器"""

    # 通用回退命名（仅用于无法读取 data.yaml 也无法从标注推断的极端情况）
    # 注意：项目已通用化，不绑定任何具体业务场景；如需自定义类别名，
    # 请在数据集 data.yaml 中显式声明 nc + names，或在调用 ConfigGenerator
    # 时通过 class_names 参数传入。
    DEFAULT_CLASS_NAMES: list[str] | None = None

    def __init__(self, base_dir: str = None):
        self.base_dir = (
            Path(base_dir).expanduser().resolve()
            if base_dir
            else Path(__file__).resolve().parent.parent
        )
        self.dataset_base = self.base_dir / "dataset"
        self.runs_dir = self.base_dir / "runs" / "detect"
        self.basemodels_dir = self.base_dir / "basemodels"
        self.configs_dir = self.base_dir / "configs"
        self.models_config_dir = self.configs_dir / "models"
        self.train_config_dir = self.configs_dir / "train"

    def resolve_model_path(self, model: str) -> str:
        """解析模型路径（委托给公共工具函数）"""
        return resolve_model_path(model, self.basemodels_dir)

    def _project_relative_path(self, path: str | Path) -> str:
        """Return a portable project-relative path when ``path`` is in the project."""
        path_obj = Path(path).expanduser()
        resolved = path_obj.resolve() if path_obj.is_absolute() else (self.base_dir / path_obj).resolve()
        try:
            return resolved.relative_to(self.base_dir).as_posix() or "."
        except ValueError:
            # External datasets/models cannot be made project-relative without copying them.
            return resolved.as_posix()

    def discover_datasets(self) -> list[str]:
        """发现dataset目录下的所有数据集"""
        datasets = []
        if self.dataset_base.exists():
            for item in self.dataset_base.iterdir():
                if item.is_dir() and (item / "images").exists():
                    datasets.append(item.name)
        return datasets

    def generate_data_yaml(
        self,
        dataset_name: str,
        class_names: list[str] | None = None,
        output_path: str | None = None,
    ) -> str:
        """
        生成data.yaml配置文件

        Args:
            dataset_name: 数据集子目录名称
            class_names: 类别名称列表，None则自动推断
            output_path: 输出路径，None则保存到项目根目录

        Returns:
            生成的yaml文件路径
        """
        dataset_path = self.dataset_base / dataset_name
        if not dataset_path.exists():
            raise FileNotFoundError(f"数据集不存在: {dataset_path}")

        # 确定输出路径。data.yaml 中的 path 相对于该文件保存，项目移动后仍有效。
        if output_path is None:
            self.models_config_dir.mkdir(parents=True, exist_ok=True)
            output_path = self.models_config_dir / f"data_{dataset_name}.yaml"
        else:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

        # 推断类别信息
        if class_names is None:
            nc, names = self._infer_classes(dataset_path)
        else:
            names = class_names
            nc = len(class_names)

        # 检查test目录是否存在
        has_test = (dataset_path / "images" / "test").exists()

        # 构建配置（使用 POSIX 路径格式确保跨平台兼容）
        relative_dataset_path = Path(os.path.relpath(
            dataset_path.resolve(),
            output_path.parent.resolve(),
        )).as_posix()
        config = DatasetConfig(
            # Omitting path makes Ultralytics use the YAML directory as its base.
            path="",
            train=f"{relative_dataset_path}/images/train",
            val=f"{relative_dataset_path}/images/val",
            test=f"{relative_dataset_path}/images/test" if has_test else None,
            nc=nc,
            names=names,
        )

        # 写入文件
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(config.to_yaml())

        return str(output_path)

    def generate_training_config(
        self,
        dataset_name: str,
        model: str = "yolov8s.pt",
        imgsz: int = 640,
        batch: int = 16,
        epochs: int = 150,
        overrides: dict[str, Any] | None = None,
    ) -> TrainingConfig:
        """
        生成训练配置

        Args:
            dataset_name: 数据集名称
            model: 预训练模型
            imgsz: 输入图像尺寸
            batch: 批次大小
            epochs: 训练轮数
            overrides: 额外覆盖参数

        Returns:
            TrainingConfig对象
        """
        config = TrainingConfig(
            model=self.resolve_model_path(model),
            imgsz=imgsz,
            batch=batch,
            epochs=epochs,
        )

        # 根据数据集大小自动调整
        dataset_path = self.dataset_base / dataset_name
        train_images = self._count_images(dataset_path, "train")

        # 自适应 workers：避免 CPU 瓶颈
        cpu_count = os.cpu_count() or 8
        config.workers = min(8, max(1, cpu_count // 2))

        # 动态关闭 mosaic：按总轮数比例，至少保留 5 个 epoch
        config.close_mosaic = max(5, config.epochs // 20)

        if train_images < 100:
            # 小数据集：增强 + 冻结 backbone 减少过拟合
            config.mosaic = 1.0
            config.mixup = 0.1
            config.degrees = 5.0
            config.scale = 0.5
            config.dropout = 0.1
            config.label_smoothing = 0.05
            config.copy_paste = 0.05
            config.freeze = 10
            config.patience = min(30, max(5, config.epochs // 5))
            config.cache = True  # 小数据集优先使用 RAM 缓存
        elif train_images < 500:
            config.mosaic = 1.0
            config.mixup = 0.05
            config.degrees = 2.0
            config.scale = 0.3
            config.dropout = 0.05
            config.label_smoothing = 0.05
            config.freeze = 5
            config.patience = min(30, max(5, config.epochs // 4))

        # 应用用户覆盖
        if overrides:
            for key, value in overrides.items():
                if hasattr(config, key):
                    setattr(config, key, value)

        return config

    def generate_project_config(
        self,
        dataset_name: str,
        model: str = "yolov8s.pt",
        imgsz: int = 640,
        batch: int = 16,
        epochs: int = 150,
        class_names: list[str] | None = None,
        description: str = "",
        overrides: dict[str, Any] | None = None,
    ) -> ProjectConfig:
        """
        生成完整的项目配置

        Args:
            dataset_name: 数据集子目录名称（同时作为模型名称）
            model: 预训练模型
            imgsz: 输入图像尺寸
            batch: 批次大小
            epochs: 训练轮数
            class_names: 类别名称列表
            description: 项目描述
            overrides: 训练参数覆盖

        Returns:
            ProjectConfig对象
        """
        # 生成data.yaml
        data_yaml_path = self.generate_data_yaml(dataset_name, class_names)

        # 生成训练配置
        training_config = self.generate_training_config(
            dataset_name=dataset_name,
            model=model,
            imgsz=imgsz,
            batch=batch,
            epochs=epochs,
            overrides=overrides,
        )

        # 构建输出目录
        output_dir = self.runs_dir / f"{dataset_name}_auto"

        project_config = ProjectConfig(
            project_name=f"{dataset_name}_auto",
            dataset_name=dataset_name,
            # Keep runtime paths absolute; save_project_config() makes persisted paths portable.
            dataset_path=str(self.dataset_base / dataset_name),
            output_dir=str(output_dir),
            data_yaml_path=data_yaml_path,
            training_config=training_config,
            description=description,
        )

        return project_config

    def save_project_config(self, config: ProjectConfig, output_path: str | None = None) -> str:
        """保存项目配置到文件"""
        if output_path is None:
            self.train_config_dir.mkdir(parents=True, exist_ok=True)
            output_path = self.train_config_dir / f"{config.project_name}.yaml"
        else:
            output_path = Path(output_path)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        config_data = config.to_dict()
        for key in ("dataset_path", "output_dir", "data_yaml_path"):
            config_data[key] = self._project_relative_path(config_data[key])
        config_data["training_config"]["model"] = self._project_relative_path(
            config_data["training_config"]["model"]
        )

        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f, sort_keys=False, allow_unicode=True)

        return str(output_path)

    def _infer_classes(self, dataset_path: Path) -> tuple:
        """从标注文件或data.yaml中推断类别信息（支持类别子目录结构）"""
        # 优先检查 data.yaml 文件
        data_yaml = dataset_path / "data.yaml"
        if data_yaml.exists():
            try:
                with open(data_yaml, encoding="utf-8") as f:
                    yaml_data = yaml.safe_load(f)
                if yaml_data and "names" in yaml_data and "nc" in yaml_data:
                    return yaml_data["nc"], yaml_data["names"]
            except Exception as e:
                logger.warning(f"读取 data.yaml 失败: {e}")

        class_ids = set()

        for split in ["train", "val", "test"]:
            label_dir = dataset_path / "labels" / split
            if not label_dir.exists():
                continue

            # 递归遍历所有子目录（支持类别子目录结构）
            for label_file in label_dir.rglob("*.txt"):
                if label_file.is_file():
                    with open(label_file, encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                try:
                                    cls_id = int(line.split()[0])
                                    class_ids.add(cls_id)
                                except (ValueError, IndexError):
                                    pass

        nc = len(class_ids)
        if nc == 0:
            # 既无 data.yaml 也无标注 → 无法推断；抛出明确错误让用户显式提供
            raise ClassInferenceError(
                dataset_path=dataset_path,
                message=(
                    f"无法从数据集 {dataset_path} 推断类别：未找到 data.yaml 且标注目录为空。\n"
                    f"请在数据集根目录的 data.yaml 中显式声明 nc 和 names，"
                    f"或在调用 generate_data_yaml / generate_training_config 时通过 class_names 参数传入。"
                ),
            )

        max_id = max(class_ids)
        names = [f"class_{i}" for i in range(max_id + 1)]

        return nc, names

    def _count_images(self, dataset_path: Path, split: str) -> int:
        """统计指定split的图像数量（支持类别子目录结构）"""
        img_dir = dataset_path / "images" / split
        if not img_dir.exists():
            return 0

        count = 0
        supported_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

        # 递归遍历所有子目录（支持类别子目录结构）
        for img_file in img_dir.rglob("*"):
            if img_file.is_file() and img_file.suffix.lower() in supported_exts:
                count += 1

        return count


def quick_setup(
    dataset_name: str,
    model: str = "yolov8s.pt",
    imgsz: int = 640,
    batch: int = 16,
    epochs: int = 150,
    class_names: list[str] | None = None,
    base_dir: str | None = None,
) -> ProjectConfig:
    """
    快速设置：一键生成所有配置

    Args:
        dataset_name: 数据集子目录名称（如 'cabel-damage-mini'）
        model: 预训练模型
        imgsz: 输入图像尺寸
        batch: 批次大小
        epochs: 训练轮数
        class_names: 类别名称列表
        base_dir: 项目根目录

    Returns:
        ProjectConfig对象
    """
    generator = ConfigGenerator(base_dir)
    config = generator.generate_project_config(
        dataset_name=dataset_name,
        model=model,
        imgsz=imgsz,
        batch=batch,
        epochs=epochs,
        class_names=class_names,
        description=f"Auto-generated config for {dataset_name}",
    )

    # 保存配置
    generator.save_project_config(config)

    return config


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python config_generator.py <dataset_name> [model] [imgsz] [batch] [epochs]")
        print("示例: python config_generator.py cabel-damage-mini yolov8s.pt 640 16 150")
        sys.exit(1)

    dataset_name = sys.argv[1]
    model = sys.argv[2] if len(sys.argv) > 2 else "yolov8s.pt"
    imgsz = int(sys.argv[3]) if len(sys.argv) > 3 else 640
    batch = int(sys.argv[4]) if len(sys.argv) > 4 else 16
    epochs = int(sys.argv[5]) if len(sys.argv) > 5 else 150

    config = quick_setup(dataset_name, model, imgsz, batch, epochs)

    print("配置生成完成!")
    print(f"  数据集: {config.dataset_name}")
    print(f"  data.yaml: {config.data_yaml_path}")
    print(f"  输出目录: {config.output_dir}")
    print(f"  模型: {config.training_config.model}")
    print(f"  图像尺寸: {config.training_config.imgsz}")
    print(f"  批次: {config.training_config.batch}")
    print(f"  轮数: {config.training_config.epochs}")
