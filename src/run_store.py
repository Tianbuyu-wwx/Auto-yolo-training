"""训练产物（run）生命周期：保留 / 回收 / 归档的唯一入口。

## 为什么需要这个模块

训练产物的「保留几个、权重放哪、怎么清理」原先散在三处、口径互不一致：

- ``TrainingPipeline._cleanup_old_runs`` —— 精确正则 + 只保留 ``max_backup_runs``；
- ``TrainingService._export_best_model_and_cleanup`` —— **子串匹配** + 整目录删除；
- ``ModelRegistry``（``copy_model=False``）—— 注册记录指向 runs/ 的原位权重。

2026-09-17 的审计里，正是这种不一致造成了两类真实事故：导出数据集 ``mine`` 的职责
却删掉了 ``my-mine-other_auto``；注册表 4 条记录里 1 条指向已被清理的权重。本模块把
规则收敛成一处，三条硬约束：

1. **删除必须可恢复**：一律经 :func:`src.utils.recycle_path` 移入 ``runs/.recycle/``，
   本模块不出现 ``rmtree``；
2. **匹配必须精确**：``^{dataset}_auto(-N)?$`` / ``^{dataset}_eval(-N)?$``，绝不用子串；
3. **保留窗口按 mtime 取最新**，默认与 ``max_backup_runs=2`` 一致，且不做「导出后
   立刻清空整批 run」这类隐藏策略。

归档（``archive_best``）用 ``copy2``：``exports/<dataset>.pt`` 是数据集级交付物，
而 run 目录里的 ``best.pt`` / ``last.pt`` 原位保留 —— 结果页、下载、按 run 注册与
断点续训都指着它们。
"""
from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.utils import recycle_path

logger = logging.getLogger(__name__)

# run 目录可能落在的 Ultralytics 任务子目录（detect 为主，classify 走 train）
RUN_SUBDIRS = ("detect", "train")

# 训练报告命名：pipeline_<dataset>_<时间戳>.json / <dataset>_best_eval_<时间戳>.json
_REPORT_PREFIXES = ("pipeline_{dataset}_", "{dataset}_best_eval_")


@dataclass(frozen=True)
class RunArtifacts:
    """一个 run 目录的产物快照（只读，供控制台展示与判断按钮可用性）。"""

    run: str
    path: str
    has_best: bool
    has_last: bool
    has_results: bool
    size_bytes: int
    size_mb: float          # 仅用于展示；精确值看 size_bytes（小文件会被舍成 0.0）
    modified: str

    @property
    def resumable(self) -> bool:
        """能否从该 run 续训（需要 last.pt）"""
        return self.has_last

    def to_dict(self) -> dict:
        return {
            "run": self.run,
            "path": self.path,
            "has_best": self.has_best,
            "has_last": self.has_last,
            "has_results": self.has_results,
            "resumable": self.resumable,
            "size_bytes": self.size_bytes,
            "size_mb": self.size_mb,
            "modified": self.modified,
        }


class RunStore:
    """基于任意 base_dir 的 run 生命周期管理。"""

    RECYCLE_DIR_NAME = ".recycle"

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        self.runs_root = self.base_dir / "runs"
        self.exports_dir = self.base_dir / "exports"
        self.reports_dir = self.base_dir / "reports"

    # ------------------------------------------------------------------
    # 路径与匹配
    # ------------------------------------------------------------------
    @property
    def recycle_dir(self) -> Path:
        return self.runs_root / self.RECYCLE_DIR_NAME

    @staticmethod
    def _pattern(dataset_name: str, kind: str) -> re.Pattern[str]:
        """``{dataset}_auto(-N)?`` / ``{dataset}_eval(-N)?`` 的精确正则。

        用子串匹配会撞车：``dataset="mine"`` 曾命中 ``my-mine-other_auto``，
        把另一个数据集的全部产物一起删掉（2026-09-17 审计复现）。
        """
        return re.compile(rf"^{re.escape(dataset_name)}_{kind}(?:-\d+)?$")

    def dataset_dirs(self, dataset_name: str, *, kind: str = "auto") -> list[Path]:
        """本数据集在 runs/detect、runs/train 下的 run/eval 目录（精确匹配）"""
        pattern = self._pattern(dataset_name, kind)
        found: list[Path] = []
        for sub in RUN_SUBDIRS:
            root = self.runs_root / sub
            if root.exists():
                found.extend(p for p in root.iterdir() if p.is_dir() and pattern.match(p.name))
        return found

    # ------------------------------------------------------------------
    # 保留 / 回收
    # ------------------------------------------------------------------
    def _recycle(self, path: Path, label: str) -> Path | None:
        dest = recycle_path(path, self.recycle_dir)
        if dest is not None:
            logger.info("[RunStore] 已回收 %s: %s → runs/%s/%s",
                        label, path.name, self.RECYCLE_DIR_NAME, dest.name)
        return dest

    def enforce_retention(self, dataset_name: str, keep_runs: int = 2,
                          keep_eval: int = 1) -> list[Path]:
        """滚动保留：最新的 ``keep_runs`` 个 run / ``keep_eval`` 个 eval 目录留在原位。

        更旧的移入 ``runs/.recycle/``（可恢复）。返回被回收的目录列表。
        """
        recycled: list[Path] = []
        for kind, keep in (("auto", keep_runs), ("eval", keep_eval)):
            dirs = self.dataset_dirs(dataset_name, kind=kind)
            if len(dirs) <= keep:
                continue
            dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            logger.info("[RunStore] %s: %d 个目录，保留最新 %d 个，回收 %d 个",
                        kind, len(dirs), keep, len(dirs) - keep)
            for path in dirs[keep:]:
                dest = self._recycle(path, "run" if kind == "auto" else "eval")
                if dest is not None:
                    recycled.append(dest)
        return recycled

    def recycle_reports(self, dataset_name: str, keep_newest: int = 1) -> list[Path]:
        """把本数据集的旧报告移入 ``runs/.recycle/_reports/``，最新 ``keep_newest`` 份留在原位。

        用**前缀精确匹配**而不是 ``dataset in 文件名`` —— 后者会把名字里含同一子串的
        别的数据集的报告一起删掉（``data`` / ``_smoke_test`` 这类短名字尤其容易撞）。
        """
        if not self.reports_dir.exists():
            return []
        prefixes = tuple(p.format(dataset=dataset_name) for p in _REPORT_PREFIXES)
        matches = [
            p for p in self.reports_dir.iterdir()
            if p.is_file() and p.name.startswith(prefixes)
        ]
        if len(matches) <= keep_newest:
            return []
        matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        recycle_root = self.recycle_dir / "_reports"
        recycled: list[Path] = []
        for path in matches[keep_newest:]:
            dest = recycle_path(path, recycle_root)
            if dest is not None:
                recycled.append(dest)
        return recycled

    # ------------------------------------------------------------------
    # 归档
    # ------------------------------------------------------------------
    def export_path(self, dataset_name: str) -> Path:
        return self.exports_dir / f"{dataset_name}.pt"

    def archive_best(self, run_dir: str | Path, dataset_name: str) -> Path | None:
        """把 ``run_dir/weights/best.pt`` 复制一份到 ``exports/<dataset>.pt``。

        ``copy2`` 而不是 ``move``：run 原位必须保留 best.pt（结果页下载、按 run 注册、
        导出接口都读它），且 ``last.pt`` 也要在（断点续训）。
        返回导出文件路径；run 内没有 best.pt 时返回 ``None``。
        """
        run_dir = Path(run_dir)
        best = run_dir / "weights" / "best.pt"
        if not best.is_file():
            logger.debug("[RunStore] %s 内没有 best.pt，跳过归档", run_dir.name)
            return None
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        target = self.export_path(dataset_name)
        if target.exists():
            logger.info("[RunStore] 已覆盖已有导出件: %s", target.name)
        shutil.copy2(best, target)
        logger.info("[RunStore] 已归档 best.pt: %s（run 原位保留: %s）", target, best)
        return target

    # ------------------------------------------------------------------
    # 只读清单（供控制台）
    # ------------------------------------------------------------------
    # 评估目录（`{dataset}_eval(-N)?`）是 evaluator 的产物：没有权重、没有 results.csv，
    # 结果页要的是「训练 run 的产物去哪了」。它们的保留由 enforce_retention(keep_eval=…)
    # 负责，不出现在产物清单里。
    _EVAL_DIR_RE = re.compile(r"_eval(?:-\d+)?$")

    def list_artifacts(self, dataset_name: str | None = None) -> list[RunArtifacts]:
        """扫描 runs/ 下的训练 run 目录，返回产物快照（不写盘）。"""
        out: list[RunArtifacts] = []
        for sub in RUN_SUBDIRS:
            root = self.runs_root / sub
            if not root.exists():
                continue
            for path in sorted(root.iterdir()):
                if not path.is_dir() or path.name == self.RECYCLE_DIR_NAME:
                    continue
                if self._EVAL_DIR_RE.search(path.name):
                    continue
                if dataset_name is not None and not self._pattern(dataset_name, "auto").match(path.name):
                    continue
                out.append(self._snapshot(path))
        out.sort(key=lambda a: a.modified, reverse=True)
        return out

    def _snapshot(self, path: Path) -> RunArtifacts:
        weights = path / "weights"
        try:
            mtime = path.stat().st_mtime
            size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        except OSError:
            mtime, size = 0.0, 0
        return RunArtifacts(
            run=path.name,
            path=str(path),
            has_best=(weights / "best.pt").is_file(),
            has_last=(weights / "last.pt").is_file(),
            has_results=(path / "results.csv").is_file(),
            size_bytes=size,
            size_mb=round(size / (1024 * 1024), 2),
            modified=datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M") if mtime else "",
        )

    def describe_export(self, dataset_name: str) -> dict | None:
        """``exports/<dataset>.pt`` 的存在性与元信息（数据集级交付物）"""
        target = self.export_path(dataset_name)
        if not target.is_file():
            return None
        stat = target.stat()
        return {
            "path": str(target),
            "size_bytes": stat.st_size,
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
        }
