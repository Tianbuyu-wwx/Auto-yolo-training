"""runtime_env 的 dev 态行为与向上探测逻辑（不真打包）。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import runtime_env  # noqa: E402


def test_dev_mode_is_not_frozen():
    assert runtime_env.is_frozen() is False


def test_project_root_is_repo_root():
    root = runtime_env.project_root()
    assert (root / "pyproject.toml").is_file()
    assert (root / "src" / "launcher").is_dir()


def test_worker_python_is_current_interpreter():
    assert runtime_env.worker_python_cmd() == [sys.executable]


def test_search_upward_finds_project(tmp_path):
    """假项目布局：从两层深的位置向上应能探测到项目根。"""
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    (tmp_path / "src" / "launcher").mkdir(parents=True)
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    assert runtime_env._search_upward(deep) == tmp_path.resolve()


def test_search_upward_returns_none_when_missing(tmp_path):
    deep = tmp_path / "x" / "y"
    deep.mkdir(parents=True)
    assert runtime_env._search_upward(deep) is None


def test_frozen_probe_finds_torch_interpreter(monkeypatch):
    """frozen 模拟：探测链应能找到带 torch 的解释器（本机有 C:/Python312）。"""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    runtime_env.worker_python_cmd.cache_clear()
    try:
        result = runtime_env.worker_python_cmd()
        assert result is not None, "本机应能探测到带 torch 的 Python"
        assert len(result) >= 1
    finally:
        runtime_env.worker_python_cmd.cache_clear()
