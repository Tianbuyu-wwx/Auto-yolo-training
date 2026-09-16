"""
数据集操作服务
"""

import logging
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from src.constants import ProjectPaths
from src.dataset_manager import AutoDatasetManager

logger = logging.getLogger(__name__)


class DatasetService:
    """数据集管理服务"""

    # ZIP解压安全限制
    MAX_ZIP_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
    MAX_ZIP_FILE_COUNT = 100000
    MAX_SINGLE_FILE_SIZE = 500 * 1024 * 1024  # 500MB

    SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.paths = ProjectPaths(base_dir)
        self.dataset_dir = self.paths.dataset_dir
        self.manager = AutoDatasetManager(str(self.dataset_dir))

    def list_datasets(self) -> list[str]:
        """列出所有可用于训练的数据集（判定：存在 data.yaml）"""
        return self.manager.list_ready_datasets()

    def get_all_statuses(self) -> list[dict]:
        """获取所有数据集状态

        注意这里是**两级口径**，二者会不一致，调用方不能混用：

        - ``is_ready``：扫描级 —— 磁盘上有 YOLO 结构（labels 目录 + 标注文件数 > 0）。
          它只说明"文件长得像 YOLO 格式"，不代表能训练。
        - ``is_trainable``：训练级 —— 存在 ``data.yaml``。训练管线只认这一条，
          它同时也是 ``list_datasets()`` 的判定依据。

        实测差异：``_smoke_test`` / ``cabel-damage-mini`` 有完整标注但缺 ``data.yaml``，
        因此 ``is_ready=True`` 却 ``is_trainable=False`` —— 界面若只按 ``is_ready``
        显示「就绪」，用户会在训练配置页的模型下拉里找不到它，却得不到任何解释。

        另：``is_ready`` 为真不代表数据合格 —— ``data`` 数据集 ``image_count=371``
        而 ``label_count=296``（val 集 75/75 张无标注），这类告警只出现在 ``issues`` 里，
        必须由调用方显式展示，否则用户会拿坏数据训练并相信产出的 mAP。
        """
        datasets = self.manager.scan_all_datasets()
        trainable = set(self.manager.list_ready_datasets())
        return [
            {
                "name": ds.name,
                "format": ds.format.value,
                "is_ready": ds.is_ready,
                "is_trainable": ds.name in trainable,
                "needs_conversion": ds.needs_conversion,
                "image_count": ds.image_count,
                "label_count": ds.label_count,
                "classes": ds.classes,
                "issues": ds.issues,
            }
            for ds in datasets
        ]

    def get_info(self, dataset_name: str) -> dict[str, Any]:
        """获取数据集详情"""
        dataset_path = self.dataset_dir / dataset_name
        if not dataset_path.exists():
            return {"error": f"数据集不存在: {dataset_name}"}

        info = {"name": dataset_name, "path": str(dataset_path), "splits": {}}

        for split in ["train", "val", "test"]:
            img_dir = dataset_path / "images" / split
            label_dir = dataset_path / "labels" / split

            img_count = 0
            label_count = 0

            if img_dir.exists():
                img_count = len(
                    [
                        f
                        for f in img_dir.rglob("*")
                        if f.suffix.lower() in self.SUPPORTED_IMAGE_EXTS and f.is_file()
                    ]
                )

            if label_dir.exists():
                label_count = len([f for f in label_dir.rglob("*.txt") if f.is_file()])

            info["splits"][split] = {
                "images": img_count,
                "labels": label_count,
            }

        info["total_images"] = sum(s["images"] for s in info["splits"].values())

        # 获取样本图像
        sample_images = []
        train_dir = dataset_path / "images" / "train"
        if train_dir.exists():
            for img in list(train_dir.iterdir())[:4]:
                if img.suffix.lower() in self.SUPPORTED_IMAGE_EXTS:
                    sample_images.append(str(img))

        info["sample_images"] = sample_images
        return info

    def extract(
        self, zip_path: str, dataset_name: str | None = None, overwrite: bool = False
    ) -> dict[str, str]:
        """解压数据集ZIP

        Args:
            zip_path: ZIP 文件路径
            dataset_name: 目标数据集名称，None 时取 ZIP 文件名
            overwrite: 同名数据集已存在时是否覆盖（False 时拒绝，防误删）
        """
        zip_path = Path(zip_path)
        if not zip_path.exists():
            return {"status": "error", "message": f"文件不存在: {zip_path}"}

        if not dataset_name:
            dataset_name = zip_path.stem

        target_dir = self.dataset_dir / dataset_name

        if target_dir.exists() and not overwrite:
            return {
                "status": "exists",
                "message": f"数据集 '{dataset_name}' 已存在。"
                "请勾选「覆盖同名数据集」后重新上传，或改用其他名称。",
                "dataset_name": dataset_name,
            }

        try:
            if target_dir.exists():
                shutil.rmtree(target_dir)

            with zipfile.ZipFile(zip_path, "r") as zf:
                total_size = sum(info.file_size for info in zf.infolist())
                if total_size > self.MAX_ZIP_SIZE:
                    return {
                        "status": "error",
                        "message": f"ZIP文件过大（{total_size / (1024**3):.1f}GB），超过2GB限制",
                    }

                if len(zf.infolist()) > self.MAX_ZIP_FILE_COUNT:
                    return {
                        "status": "error",
                        "message": f"ZIP内文件数量过多（{len(zf.infolist())}），超过100000限制",
                    }

                for info in zf.infolist():
                    if info.filename.startswith("/") or ".." in info.filename.split("/"):
                        return {"status": "error", "message": f"ZIP包含不安全路径: {info.filename}"}
                    if info.file_size > self.MAX_SINGLE_FILE_SIZE:
                        return {
                            "status": "error",
                            "message": f"文件过大: {info.filename}（{info.file_size / (1024**2):.0f}MB）",
                        }

                zf.extractall(target_dir)

            # 处理嵌套目录
            for _ in range(5):
                if not self._flatten_nested_dir(target_dir):
                    break

            return {
                "status": "success",
                "message": f"数据集 '{dataset_name}' 解压成功",
                "path": str(target_dir),
                "dataset_name": dataset_name,
            }

        except Exception as e:
            return {"status": "error", "message": f"解压失败: {str(e)}"}

    def validate(self, dataset_name: str) -> dict[str, Any]:
        """验证数据集"""
        dataset_path = self.dataset_dir / dataset_name
        if not dataset_path.exists():
            return {"status": "error", "message": f"数据集不存在: {dataset_name}"}

        try:
            import io

            old_stderr = sys.stderr
            sys.stderr = io.StringIO()

            from src.data_validator import validate_dataset

            report = validate_dataset(str(dataset_path))

            sys.stderr = old_stderr

            errors = report.get_errors()
            warnings_list = report.get_warnings()

            warning_categories = {}
            for w in warnings_list:
                cat = w.category
                warning_categories[cat] = warning_categories.get(cat, 0) + 1

            error_categories = {}
            for e in errors:
                cat = e.category
                error_categories[cat] = error_categories.get(cat, 0) + 1

            return {
                "status": "success" if report.is_valid else "warning",
                "is_valid": report.is_valid,
                "error_count": len(errors),
                "warning_count": len(warnings_list),
                "error_categories": error_categories,
                "warning_categories": warning_categories,
                "stats": report.stats,
                "message": self._format_validation_message(report, errors, warnings_list),
            }

        except Exception as e:
            sys.stderr = old_stderr
            return {"status": "error", "message": f"验证失败: {str(e)}"}

    def get_annotated_samples(self, dataset_name: str, count: int = 4) -> list[str]:
        """生成画好标注框的样本图，返回缓存路径列表（P2-5 标注可视化）。

        YOLO bbox 标签（cls cx cy w h，归一化）→ 画到图像上，
        缓存到 logs/preview_cache/<dataset>/。seg/pose 标签退化为最小外接矩形。
        """
        dataset_path = self.dataset_dir / dataset_name
        train_img_dir = dataset_path / "images" / "train"
        train_lbl_dir = dataset_path / "labels" / "train"
        if not train_img_dir.exists():
            return []

        try:
            from PIL import Image, ImageDraw
        except ImportError:
            logger.debug("[PREVIEW] PIL 不可用，跳过标注可视化")
            return []

        # 类名（用于标签文本）
        class_names: dict[int, str] = {}
        for yaml_path in (
            dataset_path / "data.yaml",
            self.base_dir / "configs" / "models" / f"data_{dataset_name}.yaml",
        ):
            if yaml_path.exists():
                try:
                    import yaml

                    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
                    class_names = dict(enumerate(data.get("names", [])))
                    break
                except Exception:
                    continue

        colors = [
            "#FF3B30",
            "#34C759",
            "#007AFF",
            "#FFCC00",
            "#AF52DE",
            "#FF9500",
            "#00C7BE",
            "#FF2D55",
        ]

        cache_dir = self.base_dir / "logs" / "preview_cache" / dataset_name
        cache_dir.mkdir(parents=True, exist_ok=True)

        images = [
            f
            for f in sorted(train_img_dir.rglob("*"))
            if f.suffix.lower() in self.SUPPORTED_IMAGE_EXTS
        ][:count]
        out: list[str] = []
        for img_path in images:
            label_path = train_lbl_dir / f"{img_path.stem}.txt"
            out_path = cache_dir / f"{img_path.stem}_boxed{img_path.suffix or '.png'}"
            try:
                with Image.open(img_path) as im:
                    im = im.convert("RGB")
                    w, h = im.size
                    if label_path.exists():
                        draw = ImageDraw.Draw(im)
                        for line in label_path.read_text(encoding="utf-8").splitlines():
                            parts = line.split()
                            if len(parts) < 5:
                                continue
                            cls_id = int(float(parts[0]))
                            try:
                                cx, cy, bw, bh = (float(x) for x in parts[1:5])
                            except ValueError:
                                continue
                            # seg/pose 多点标签：取所有坐标的最小外接矩形
                            if len(parts) > 5:
                                coords = [float(x) for x in parts[1:] if float(x) <= 1.0]
                                xs, ys = coords[0::2], coords[1::2]
                                if not xs or not ys:
                                    continue
                                x1, x2 = min(xs) * w, max(xs) * w
                                y1, y2 = min(ys) * h, max(ys) * h
                                bw, bh, cx, cy = x2 - x1, y2 - y1, (x1 + x2) / 2, (y1 + y2) / 2
                                x1, y1 = cx - bw / 2, cy - bh / 2
                            else:
                                x1 = (cx - bw / 2) * w
                                y1 = (cy - bh / 2) * h
                                x2, y2 = (cx + bw / 2) * w, (cy + bh / 2) * h
                            color = colors[cls_id % len(colors)]
                            draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
                            if class_names:
                                draw.text(
                                    (x1 + 2, max(0, y1 - 12)),
                                    class_names.get(cls_id, str(cls_id)),
                                    fill=color,
                                )
                    im.save(out_path)
                out.append(str(out_path))
            except Exception as e:
                logger.debug("[PREVIEW] 生成标注预览失败 %s: %s", img_path.name, e)
        return out

    def convert(self, dataset_name: str, delete_original: bool = False) -> dict[str, Any]:
        """分类格式 → YOLO 格式转换（显式触发，不在启动时自动执行）

        Args:
            dataset_name: 待转换数据集名称
            delete_original: 转换成功后是否删除原始数据集（默认保留）

        Returns:
            ``{"status": "success"/"error", "message": ..., 转换详情...}``
        """
        try:
            result = self.manager.convert_dataset(dataset_name, delete_original=delete_original)
        except ValueError as e:
            return {"status": "error", "message": str(e)}
        except Exception as e:
            logger.exception("[CONVERT] 转换异常: %s", e)
            return {"status": "error", "message": f"转换失败: {e}"}

        if not result.get("success"):
            return {"status": "error", "message": result.get("message", "无需转换")}

        stats = result.get("stats", {})
        stat_line = "、".join(f"{split} {count} 张" for split, count in stats.items())
        message = (
            f"{result.get('message', '转换成功')} → 「{result.get('converted_name', '')}」"
            + (f"（{stat_line}）" if stat_line else "")
        )
        if delete_original:
            message += "。原始数据集已删除。"
        return {
            "status": "success",
            "message": message,
            "converted_name": result.get("converted_name"),
            "stats": stats,
        }

    def get_pending_conversion(self) -> list[str]:
        """列出需要分类→YOLO 转换的数据集名称"""
        return [ds.name for ds in self.manager.scan_all_datasets() if ds.needs_conversion]

    # ------------------------------------------------------------------
    # 删除 / 回收站
    # ------------------------------------------------------------------
    # 回收目录以点开头：scan_all_datasets() 与 list_ready_datasets() 都会跳过
    # 「以 . 开头的目录」，所以回收站不会被当成一个数据集列进控制台。
    RECYCLE_DIR_NAME = ".recycle"

    @property
    def recycle_dir(self) -> Path:
        return self.dataset_dir / self.RECYCLE_DIR_NAME

    def _resolve_dataset(self, dataset_name: str) -> Path | None:
        """把数据集名解析成 dataset/ 下的直接子目录；越界或不存在返回 None。

        数据集名来自 URL 路径，必须挡住 `../` 之类的穿越写法。
        """
        if not dataset_name or dataset_name in (".", ".."):
            return None
        try:
            candidate = (self.dataset_dir / dataset_name).resolve()
        except OSError:
            return None
        if candidate.parent != self.dataset_dir.resolve() or not candidate.is_dir():
            return None
        return candidate

    def delete(self, dataset_name: str) -> dict[str, Any]:
        """删除数据集 —— 实际是**移入回收目录**，可以恢复。

        为什么不用 `rmtree`：删数据集不可逆，而控制台上一次误点就足以触发。
        移入 `dataset/.recycle/<名称>_<时间戳>/` 后仍可 `restore()` 回来，
        代价只是多占一份磁盘（用户想彻底清掉时自行删该目录即可）。

        同时清掉 `logs/preview_cache/<名称>/`：那是按数据集名缓存的画框图，
        留着会在重建同名数据集时显示旧图。

        Returns:
            ``{"status": "success"/"error", "message": ..., "recycled_to": ...}``
        """
        src = self._resolve_dataset(dataset_name)
        if src is None:
            return {"status": "error", "message": f"数据集不存在: {dataset_name}"}

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = self.recycle_dir / f"{dataset_name}_{stamp}"
        try:
            self.recycle_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
        except OSError as e:
            logger.exception("[DELETE] 移入回收目录失败: %s", e)
            return {"status": "error", "message": f"删除失败: {e}"}

        preview = self.paths.logs_dir / "preview_cache" / dataset_name
        if preview.is_dir():
            shutil.rmtree(preview, ignore_errors=True)

        return {
            "status": "success",
            "message": f"已删除「{dataset_name}」，可在回收目录中恢复",
            "recycled_to": str(dest),
            "recycled_name": dest.name,
        }

    def list_recycled(self) -> list[dict[str, Any]]:
        """列出回收目录里的数据集（最近删除在前）"""
        if not self.recycle_dir.is_dir():
            return []
        items = []
        for entry in self.recycle_dir.iterdir():
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            try:
                size_mb = round(
                    sum(f.stat().st_size for f in entry.rglob("*") if f.is_file()) / (1024 * 1024),
                    2,
                )
                mtime = entry.stat().st_mtime
            except OSError:
                size_mb, mtime = 0.0, 0.0
            items.append(
                {
                    "recycled_name": entry.name,
                    "original_name": self._original_name(entry.name),
                    "size_mb": size_mb,
                    "mtime": mtime,
                    "recycled_at": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
                    if mtime
                    else "",
                }
            )
        items.sort(key=lambda d: d["mtime"], reverse=True)
        for d in items:
            del d["mtime"]  # 仅用于排序，不外传
        return items

    @staticmethod
    def _original_name(recycled_name: str) -> str:
        """从 `<名称>_<YYYYmmdd>_<HHMMSS>` 还原原数据集名。

        名字由 `delete()` 生成，所以这个解析是确定的；但**如果用户手工重命名过
        回收目录**，这里就只能按重命名后的结果猜 —— 属于已知限制。
        """
        parts = recycled_name.rsplit("_", 2)
        return parts[0] if len(parts) == 3 and len(parts[1]) == 8 else recycled_name

    def restore(self, recycled_name: str) -> dict[str, Any]:
        """把回收目录里的数据集恢复回 `dataset/<原名称>`"""
        if not recycled_name or recycled_name in (".", ".."):
            return {"status": "error", "message": "回收项名称非法"}
        src = (self.recycle_dir / recycled_name).resolve()
        if src.parent != self.recycle_dir.resolve() or not src.is_dir():
            return {"status": "error", "message": f"回收项不存在: {recycled_name}"}

        original = self._original_name(recycled_name)
        dest = self.dataset_dir / original
        if dest.exists():
            return {"status": "error", "message": f"「{original}」已存在，请先改名或删除它再恢复"}
        try:
            shutil.move(str(src), str(dest))
        except OSError as e:
            logger.exception("[RESTORE] 恢复失败: %s", e)
            return {"status": "error", "message": f"恢复失败: {e}"}
        return {"status": "success", "message": f"已恢复为「{original}」", "restored_to": str(dest)}

    def _flatten_nested_dir(self, target_dir: Path) -> bool:
        """处理嵌套目录"""
        dataset_root = self._find_dataset_root(target_dir)
        if dataset_root == target_dir:
            return False

        for item in dataset_root.iterdir():
            dest = target_dir / item.name
            if dest.exists():
                shutil.rmtree(dest) if dest.is_dir() else dest.unlink()
            shutil.move(str(item), str(dest))

        current = dataset_root
        while current != target_dir:
            parent = current.parent
            current.rmdir()
            current = parent
        return True

    def _find_dataset_root(self, path: Path, depth: int = 0) -> Path:
        """递归查找包含 images/train 的目录"""
        if depth > 5:
            return path
        if (path / "images" / "train").exists():
            return path
        subdirs = [d for d in path.iterdir() if d.is_dir()]
        if len(subdirs) == 1:
            return self._find_dataset_root(subdirs[0], depth + 1)
        return path

    def _format_validation_message(self, report, errors, warnings_list) -> str:
        lines = []
        if not report.is_valid:
            lines.append("数据验证未通过，存在阻塞性问题")
        elif warnings_list:
            lines.append("数据验证通过，但存在建议优化项")
        else:
            lines.append("数据验证完全通过")

        cat_names = {
            "directory_structure": "目录结构",
            "image_format": "图像格式",
            "image_read_failed": "图像读取失败",
            "image_dimension": "图像尺寸异常",
            "label_format": "标注格式错误",
            "label_out_of_bounds": "标注值越界",
            "label_zero_size": "标注框尺寸为零",
            "missing_label": "缺少标注文件",
            "orphan_label": "孤立标注文件",
            "class_mismatch": "类别不匹配",
            "config_error": "配置文件错误",
            "dataset_size": "数据集规模",
            "split_ratio": "划分比例",
            "class_imbalance": "类别不平衡",
        }

        if errors:
            lines.append(f"\n**错误 ({len(errors)}个):**")
            for e in errors:
                lines.append(f"  - {cat_names.get(e.category, e.category)}: {e.message[:80]}")

        if warnings_list:
            lines.append(f"\n**警告 ({len(warnings_list)}个):**")
            grouped = {}
            for w in warnings_list:
                name = cat_names.get(w.category, w.category)
                grouped[name] = grouped.get(name, 0) + 1
            for name, count in grouped.items():
                lines.append(f"  - {name}: {count}个")

        stats = report.stats
        if "splits" in stats:
            lines.append("\n**数据集统计:**")
            for split, data in stats["splits"].items():
                if data.get("images", 0) > 0:
                    lines.append(
                        f"  - {split}: {data['images']}张图像, {data.get('labels', 0)}个标注"
                    )

        return "\n".join(lines)
