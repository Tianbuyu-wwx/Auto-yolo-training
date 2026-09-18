"""数据集清单：指纹、差异描述、CLI 往返。

清单的用途是回答"这次训练用的还是上次那份数据吗"，所以判据不是"函数返回了 dict"，
而是：**改一个文件/加一个文件/换一个划分，都要被指出来且说得清是什么变了**。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from dataset_manifest import (  # noqa: E402
    MANIFEST_NAME,
    build_manifest,
    diff_manifests,
    main,
)


def make_dataset(root: Path, name: str = "ds") -> Path:
    d = root / name
    (d / "images" / "train").mkdir(parents=True)
    (d / "labels" / "train").mkdir(parents=True)
    for i in range(3):
        (d / "images" / "train" / f"a{i}.jpg").write_bytes(b"x" * (10 + i))
        (d / "labels" / "train" / f"a{i}.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    (d / "data.yaml").write_text("path: .\n", encoding="utf-8")
    return d


def test_counts_images_and_labels(tmp_path: Path) -> None:
    make_dataset(tmp_path)
    m = build_manifest(tmp_path)
    ds = m["datasets"]["ds"]
    assert ds["images"] == 3
    assert ds["labels"] == 3
    assert ds["files"] == 7          # 3 图 + 3 标 + data.yaml
    assert ds["splits"] == ["images", "labels"]


def test_manifest_file_itself_is_not_counted(tmp_path: Path) -> None:
    """清单写回数据集目录里，不能把自己算成数据（否则每次 --write 都"变化"）"""
    make_dataset(tmp_path)
    first = build_manifest(tmp_path)
    (tmp_path / MANIFEST_NAME).write_text("{}", encoding="utf-8")
    again = build_manifest(tmp_path)
    assert first == again


def test_digest_changes_when_a_label_is_rewritten(tmp_path: Path) -> None:
    make_dataset(tmp_path)
    before = build_manifest(tmp_path)
    (tmp_path / "ds" / "labels" / "train" / "a1.txt").write_text(
        "0 0.1 0.1 0.1 0.1\n", encoding="utf-8")
    after = build_manifest(tmp_path)
    assert before["datasets"]["ds"]["digest"] != after["datasets"]["ds"]["digest"]
    # 文件数没变，但内容变了 —— 差异描述必须仍能指出"内容变化"
    msgs = diff_manifests(before, after)
    assert len(msgs) == 1
    assert "内容变化：ds" in msgs[0]


def test_diff_reports_added_and_removed(tmp_path: Path) -> None:
    make_dataset(tmp_path, "keep")
    old = build_manifest(tmp_path)
    make_dataset(tmp_path, "fresh")
    (tmp_path / "keep" / "data.yaml").unlink()
    (tmp_path / "keep").rename(tmp_path / "gone")
    new = build_manifest(tmp_path)
    msgs = "\n".join(diff_manifests(old, new))
    assert "新增数据集：fresh" in msgs
    assert "数据集消失：keep" in msgs


def test_cli_write_then_check_roundtrip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_dataset(tmp_path)
    assert main(["--dir", str(tmp_path), "--write"]) == 0
    assert (tmp_path / MANIFEST_NAME).is_file()
    assert main(["--dir", str(tmp_path), "--check"]) == 0
    assert "完全相同" in capsys.readouterr().out

    # 改动之后 check 必须非 0 退出（CI/脚本才能拿它当门禁）
    (tmp_path / "ds" / "images" / "train" / "new.jpg").write_bytes(b"y")
    assert main(["--dir", str(tmp_path), "--check"]) == 1
    assert "内容变化：ds" in capsys.readouterr().out


def test_check_without_manifest_is_an_error(tmp_path: Path) -> None:
    make_dataset(tmp_path)
    assert main(["--dir", str(tmp_path), "--check"]) == 2


def test_sha256_mode_is_stable_across_mtime_touch(tmp_path: Path) -> None:
    """--hash 模式的用途：mtime 变了但内容没变时不该判成漂移"""
    make_dataset(tmp_path)
    h1 = build_manifest(tmp_path, use_hash=True)
    import os
    import time
    for f in (tmp_path / "ds").rglob("*"):
        if f.is_file():
            os.utime(f, (time.time(), time.time()))
    h2 = build_manifest(tmp_path, use_hash=True)
    assert h1 == h2
