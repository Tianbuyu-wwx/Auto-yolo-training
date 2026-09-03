"""
模型版本管理模块
管理模型版本、元数据和血缘追踪
"""

import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class ModelVersion:
    """模型版本信息"""
    version_id: str
    model_path: str
    dataset_name: str
    created_at: str
    metrics: dict[str, float] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    description: str = ""
    parent_version: str | None = None
    status: str = "staging"  # staging / production / archived

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ModelRegistry:
    """模型注册表"""

    def __init__(self, base_dir: str | None = None):
        self.base_dir = Path(base_dir) if base_dir else Path(__file__).parent.parent
        self.registry_dir = self.base_dir / "model_registry"
        self.registry_dir.mkdir(exist_ok=True)
        self.versions_file = self.registry_dir / "versions.json"
        self.models_dir = self.registry_dir / "models"
        self.models_dir.mkdir(exist_ok=True)

        self._versions: dict[str, list[ModelVersion]] = {}
        self._load_registry()

    def _load_registry(self):
        """加载注册表"""
        if self.versions_file.exists():
            try:
                with open(self.versions_file, encoding="utf-8") as f:
                    data = json.load(f)
                for dataset_name, versions in data.items():
                    self._versions[dataset_name] = [
                        ModelVersion(**v) for v in versions
                    ]
            except Exception:
                self._versions = {}

    def _save_registry(self):
        """保存注册表"""
        data = {}
        for dataset_name, versions in self._versions.items():
            data[dataset_name] = [v.to_dict() for v in versions]

        with open(self.versions_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _generate_version_id(self, model_path: str) -> str:
        """生成版本ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_name = Path(model_path).stem
        return f"{model_name}_{timestamp}"

    def _copy_model(self, source_path: str, version_id: str) -> str:
        """复制模型到注册表"""
        dest_dir = self.models_dir / version_id
        dest_dir.mkdir(exist_ok=True)
        dest_path = dest_dir / "model.pt"
        shutil.copy2(source_path, dest_path)
        return str(dest_path)

    def register(
        self,
        model_path: str,
        dataset_name: str,
        metrics: dict[str, float] | None = None,
        params: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        description: str = "",
        parent_version: str | None = None,
        copy_model: bool = True,
    ) -> ModelVersion:
        """
        注册新模型版本

        Args:
            model_path: 模型文件路径
            dataset_name: 数据集名称
            metrics: 评估指标
            params: 训练参数
            tags: 标签列表
            description: 描述
            parent_version: 父版本ID
            copy_model: 是否复制模型到注册表

        Returns:
            ModelVersion对象
        """
        version_id = self._generate_version_id(model_path)

        # 复制模型
        if copy_model:
            registry_path = self._copy_model(model_path, version_id)
        else:
            registry_path = model_path

        version = ModelVersion(
            version_id=version_id,
            model_path=registry_path,
            dataset_name=dataset_name,
            created_at=datetime.now().isoformat(),
            metrics=metrics or {},
            params=params or {},
            tags=tags or [],
            description=description,
            parent_version=parent_version,
            status="staging",
        )

        # 添加到注册表
        if dataset_name not in self._versions:
            self._versions[dataset_name] = []
        self._versions[dataset_name].append(version)

        # 保存
        self._save_registry()

        return version

    def get_versions(self, dataset_name: str) -> list[ModelVersion]:
        """获取数据集的所有版本"""
        return self._versions.get(dataset_name, [])

    def get_version(self, dataset_name: str, version_id: str) -> ModelVersion | None:
        """获取特定版本"""
        versions = self._versions.get(dataset_name, [])
        for v in versions:
            if v.version_id == version_id:
                return v
        return None

    def get_latest(self, dataset_name: str, status: str | None = None) -> ModelVersion | None:
        """获取最新版本"""
        versions = self._versions.get(dataset_name, [])
        if status:
            versions = [v for v in versions if v.status == status]
        if not versions:
            return None
        return max(versions, key=lambda v: v.created_at)

    def get_best(self, dataset_name: str, metric: str = "mAP50") -> ModelVersion | None:
        """获取最佳版本（按指标）"""
        versions = self._versions.get(dataset_name, [])
        if not versions:
            return None

        valid_versions = [v for v in versions if metric in v.metrics]
        if not valid_versions:
            return None

        return max(valid_versions, key=lambda v: v.metrics[metric])

    def update_status(self, dataset_name: str, version_id: str, status: str) -> bool:
        """更新版本状态"""
        version = self.get_version(dataset_name, version_id)
        if version is None:
            return False

        version.status = status
        self._save_registry()
        return True

    def promote_to_production(self, dataset_name: str, version_id: str) -> bool:
        """提升版本到生产环境"""
        # 先将该数据集的所有生产版本降级
        versions = self._versions.get(dataset_name, [])
        for v in versions:
            if v.status == "production":
                v.status = "archived"

        # 提升指定版本
        return self.update_status(dataset_name, version_id, "production")

    def add_tags(self, dataset_name: str, version_id: str, tags: list[str]) -> bool:
        """添加标签"""
        version = self.get_version(dataset_name, version_id)
        if version is None:
            return False

        version.tags.extend(tags)
        version.tags = list(set(version.tags))  # 去重
        self._save_registry()
        return True

    def compare_versions(self, dataset_name: str, version_id1: str, version_id2: str) -> dict[str, Any]:
        """对比两个版本"""
        v1 = self.get_version(dataset_name, version_id1)
        v2 = self.get_version(dataset_name, version_id2)

        if v1 is None or v2 is None:
            return {"error": "Version not found"}

        comparison = {
            "version1": v1.version_id,
            "version2": v2.version_id,
            "metrics_diff": {},
            "params_diff": {},
        }

        # 对比指标
        all_metrics = set(v1.metrics.keys()) | set(v2.metrics.keys())
        for metric in all_metrics:
            m1 = v1.metrics.get(metric, 0)
            m2 = v2.metrics.get(metric, 0)
            comparison["metrics_diff"][metric] = {
                "v1": m1,
                "v2": m2,
                "diff": round(m2 - m1, 6),
            }

        # 对比参数
        all_params = set(v1.params.keys()) | set(v2.params.keys())
        for param in all_params:
            p1 = v1.params.get(param)
            p2 = v2.params.get(param)
            if p1 != p2:
                comparison["params_diff"][param] = {"v1": p1, "v2": p2}

        return comparison

    def list_all(self) -> dict[str, list[dict[str, Any]]]:
        """列出所有注册模型"""
        return {
            dataset_name: [v.to_dict() for v in versions]
            for dataset_name, versions in self._versions.items()
        }

    def get_production_model(self, dataset_name: str) -> str | None:
        """获取生产环境模型路径"""
        versions = self._versions.get(dataset_name, [])
        for v in versions:
            if v.status == "production":
                return v.model_path
        return None

    def delete_version(self, dataset_name: str, version_id: str) -> bool:
        """删除版本"""
        versions = self._versions.get(dataset_name, [])
        version = self.get_version(dataset_name, version_id)
        if version is None:
            return False

        # 删除模型文件
        model_dir = self.models_dir / version_id
        if model_dir.exists():
            shutil.rmtree(model_dir)

        # 从注册表移除
        self._versions[dataset_name] = [v for v in versions if v.version_id != version_id]
        self._save_registry()
        return True


def quick_register(
    model_path: str,
    dataset_name: str,
    metrics: dict[str, float] | None = None,
    base_dir: str | None = None,
) -> ModelVersion:
    """
    快速注册便捷函数

    Args:
        model_path: 模型文件路径
        dataset_name: 数据集名称
        metrics: 评估指标
        base_dir: 项目根目录

    Returns:
        ModelVersion对象
    """
    registry = ModelRegistry(base_dir)
    return registry.register(
        model_path=model_path,
        dataset_name=dataset_name,
        metrics=metrics,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="模型版本管理")
    parser.add_argument("--list", action="store_true", help="列出所有模型")
    parser.add_argument("--register", help="注册模型路径")
    parser.add_argument("--dataset", default="unknown", help="数据集名称")
    parser.add_argument("--metrics", help="指标JSON字符串")
    parser.add_argument("--promote", help="提升到生产环境的版本ID")
    parser.add_argument("--best", action="store_true", help="显示最佳版本")

    args = parser.parse_args()

    registry = ModelRegistry()

    if args.list:
        all_models = registry.list_all()
        print(json.dumps(all_models, indent=2, ensure_ascii=False))

    elif args.register:
        metrics = json.loads(args.metrics) if args.metrics else {}
        version = registry.register(
            model_path=args.register,
            dataset_name=args.dataset,
            metrics=metrics,
        )
        print(f"Registered: {version.version_id}")
        print(f"  Dataset: {version.dataset_name}")
        print(f"  Metrics: {version.metrics}")

    elif args.promote:
        success = registry.promote_to_production(args.dataset, args.promote)
        print(f"Promote {'success' if success else 'failed'}")

    elif args.best:
        version = registry.get_best(args.dataset)
        if version:
            print(f"Best version: {version.version_id}")
            print(f"  Metrics: {version.metrics}")
        else:
            print("No versions found")
