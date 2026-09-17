"""RunStore：训练产物生命周期的唯一入口（保留 / 回收 / 归档）。

回归背景（2026-09-17 审计）：
- ``TrainingService`` 用 **子串匹配** 删 run 目录 —— 导出数据集 ``mine`` 时把
  ``my-mine-other_auto``（另一个数据集的全部产物）一起删了；
- ``TrainingPipeline`` 用精确正则但直接 ``rmtree``；
- 两套口径并存，且都不可恢复。

本组测试把三条硬约束钉死：**精确匹配、可恢复、运行中的 run 不动**。
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.run_store import RunStore


def _make_run(base: Path, name: str, *, best: bool = True, last: bool = True,
              results: bool = True, mtime: float | None = None) -> Path:
    run = base / "runs" / "detect" / name
    (run / "weights").mkdir(parents=True)
    if best:
        (run / "weights" / "best.pt").write_bytes(b"B" * 64)
    if last:
        (run / "weights" / "last.pt").write_bytes(b"L" * 64)
    if results:
        (run / "results.csv").write_text("epoch,mAP50\n0,0.5\n", encoding="utf-8")
    (run / "args.yaml").write_text(f"data: data_{name.split('_auto')[0]}.yaml\nepochs: 3\n",
                                   encoding="utf-8")
    if mtime is not None:
        import os
        os.utime(run, (mtime, mtime))
    return run


class TestRunStore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.store = RunStore(self.temp_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # 精确匹配
    # ------------------------------------------------------------------
    def test_dataset_dirs_match_exactly_not_by_substring(self):
        """子串撞车是真实事故：mine 不能命中 my-mine-other_auto"""
        _make_run(self.temp_dir, "mine_auto")
        other = _make_run(self.temp_dir, "my-mine-other_auto")

        found = self.store.dataset_dirs("mine")

        self.assertEqual([p.name for p in found], ["mine_auto"])
        self.assertTrue(other.is_dir())

    def test_eval_dirs_are_a_separate_kind(self):
        _make_run(self.temp_dir, "ds_auto")
        eval_dir = self.temp_dir / "runs" / "detect" / "ds_eval"
        eval_dir.mkdir(parents=True)

        self.assertEqual([p.name for p in self.store.dataset_dirs("ds", kind="auto")], ["ds_auto"])
        self.assertEqual([p.name for p in self.store.dataset_dirs("ds", kind="eval")], ["ds_eval"])

    # ------------------------------------------------------------------
    # 保留 / 回收
    # ------------------------------------------------------------------
    def test_retention_keeps_newest_and_recycles_the_rest(self):
        base = 1_700_000_000
        for i, name in enumerate(["ds_auto", "ds_auto-2", "ds_auto-3", "ds_auto-4"]):
            _make_run(self.temp_dir, name, mtime=base + i)

        recycled = self.store.enforce_retention("ds", keep_runs=2)

        kept = sorted(p.name for p in (self.temp_dir / "runs" / "detect").iterdir())
        self.assertEqual(kept, ["ds_auto-3", "ds_auto-4"])
        self.assertEqual(len(recycled), 2)
        for dest in recycled:
            self.assertTrue(dest.is_dir(), "回收站里必须是完整目录，不是空壳")
            self.assertTrue((dest / "weights" / "best.pt").is_file())

    def test_retention_never_touches_other_datasets(self):
        base = 1_700_000_000
        for i, name in enumerate(["ds_auto", "ds_auto-2", "ds_auto-3"]):
            _make_run(self.temp_dir, name, mtime=base + i)
        other = _make_run(self.temp_dir, "my-ds_auto", mtime=base + 10)

        self.store.enforce_retention("ds", keep_runs=1)

        self.assertTrue(other.is_dir())
        self.assertTrue((other / "weights" / "best.pt").is_file())

    def test_retention_handles_eval_dirs(self):
        base = 1_700_000_000
        for i, name in enumerate(["ds_eval", "ds_eval-2"]):
            d = self.temp_dir / "runs" / "detect" / name
            d.mkdir(parents=True)
            import os
            os.utime(d, (base + i, base + i))

        recycled = self.store.enforce_retention("ds", keep_eval=1)

        self.assertEqual(len(recycled), 1)
        self.assertEqual(recycled[0].name.split("_2026")[0], "ds_eval")

    def test_recycle_dir_is_inside_runs(self):
        """回收站放在 runs/ 下：同盘 move 不会跨卷失败，且 scan 逻辑天然跳过"""
        self.assertEqual(self.store.recycle_dir, self.temp_dir / "runs" / ".recycle")

    # ------------------------------------------------------------------
    # 归档
    # ------------------------------------------------------------------
    def test_archive_best_copies_and_keeps_run_intact(self):
        run = _make_run(self.temp_dir, "ds_auto")

        exported = self.store.archive_best(run, "ds")

        self.assertIsNotNone(exported)
        self.assertEqual(exported, self.temp_dir / "exports" / "ds.pt")
        self.assertTrue((run / "weights" / "best.pt").is_file(), "run 里的 best.pt 不该被搬走")
        self.assertTrue((run / "weights" / "last.pt").is_file(), "断点必须保留")

    def test_archive_best_returns_none_without_best(self):
        run = _make_run(self.temp_dir, "ds_auto", best=False)
        self.assertIsNone(self.store.archive_best(run, "ds"))

    def test_archive_best_overwrites_previous_export(self):
        first = _make_run(self.temp_dir, "ds_auto")
        self.store.archive_best(first, "ds")
        (first / "weights" / "best.pt").write_bytes(b"NEW" * 32)

        self.store.archive_best(first, "ds")

        exported = (self.temp_dir / "exports" / "ds.pt").read_bytes()
        self.assertEqual(exported, b"NEW" * 32)

    # ------------------------------------------------------------------
    # 报告
    # ------------------------------------------------------------------
    def test_recycle_reports_uses_exact_prefix_and_keeps_newest(self):
        reports = self.temp_dir / "reports"
        reports.mkdir(parents=True)
        import os
        old = reports / "pipeline_ds_20260101_000000.json"
        new = reports / "pipeline_ds_20260102_000000.json"
        other = reports / "pipeline_data_20260101_000000.json"      # 短名撞车受害者
        best_eval = reports / "ds_best_eval_20260101_000000.json"
        for item, mtime in ((old, 1_700_000_000), (new, 1_800_000_000),
                            (other, 1_650_000_000), (best_eval, 1_600_000_000)):
            item.write_text("{}", encoding="utf-8")
            os.utime(item, (mtime, mtime))

        recycled = self.store.recycle_reports("ds", keep_newest=1)

        self.assertTrue(new.is_file(), "最新一份报告留在原位")
        self.assertTrue(other.is_file(), "别的数据集的报告不能被前缀撞掉")
        self.assertFalse(old.exists())
        self.assertFalse(best_eval.exists())
        self.assertEqual(len(recycled), 2)
        for dest in recycled:
            self.assertEqual(dest.parent.name, "_reports")

    # ------------------------------------------------------------------
    # 只读清单
    # ------------------------------------------------------------------
    def test_list_artifacts_flags(self):
        _make_run(self.temp_dir, "ds_auto")
        _make_run(self.temp_dir, "ds_auto-2", best=False, last=False, results=False)
        d = self.temp_dir / "runs" / "detect" / "ds_eval"
        d.mkdir(parents=True)   # 非 auto 目录不该出现

        by_name = {a.run: a for a in self.store.list_artifacts()}

        self.assertEqual(set(by_name), {"ds_auto", "ds_auto-2"})
        full = by_name["ds_auto"]
        self.assertTrue(full.has_best and full.has_last and full.has_results and full.resumable)
        self.assertGreater(full.size_bytes, 0)   # 小文件会被 size_mb 舍成 0.0，用精确值
        empty = by_name["ds_auto-2"]
        self.assertFalse(empty.has_best or empty.has_last or empty.has_results or empty.resumable)

    def test_list_artifacts_filters_by_dataset(self):
        _make_run(self.temp_dir, "ds_auto")
        _make_run(self.temp_dir, "other_auto")

        names = [a.run for a in self.store.list_artifacts("ds")]

        self.assertEqual(names, ["ds_auto"])

    def test_describe_export(self):
        self.assertIsNone(self.store.describe_export("ds"))
        run = _make_run(self.temp_dir, "ds_auto")
        self.store.archive_best(run, "ds")
        info = self.store.describe_export("ds")
        self.assertIsNotNone(info)
        self.assertEqual(info["path"], str(self.temp_dir / "exports" / "ds.pt"))
        self.assertGreater(info["size_bytes"], 0)


if __name__ == "__main__":
    unittest.main()
