"""安装器纯逻辑测试：版本比较 / 命令构造 / 计划与动作序列（全部无副作用）。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from installer.ayt_setup import execute as ex  # noqa: E402
from installer.ayt_setup.plan import build_plan  # noqa: E402
from installer.ayt_setup.scan import REQUIRED_PACKAGES, satisfies  # noqa: E402


def _rep(**over):
    """制造一份最小扫描报告；over 覆盖顶层键。"""
    base = {
        "interpreters": [
            {"path": "C:/Python312/python.exe", "version": "3.12.7", "source": "common path"}
        ],
        "gpu": {
            "present": True,
            "gpus": [{"name": "RTX 5080", "memory": "16303 MiB", "driver": "610.74"}],
        },
        "webview2": {"present": True, "version": "154.0"},
        "disk": {"path": "C:/", "free_gb": 100.0, "total_gb": 500.0},
        "network": {"pypi": {"ok": True}, "tuna": {"ok": True}, "pytorch_cu128": {"ok": True}},
        "install": {
            "install_dir": "X",
            "dir_exists": False,
            "venv_present": False,
            "venv_python": None,
            "launcher_present": False,
        },
        "selected_python": "C:/Python312/python.exe",
        "packages": dict.fromkeys(REQUIRED_PACKAGES, "9.9"),
        "torch_cuda": {"installed": True, "version": "2.9", "cuda": "13.0", "available": True},
    }
    base.update(over)
    return base


def test_satisfies():
    assert satisfies("3.12.7", "3.12")
    assert satisfies("6.2.1", "6.2")
    assert not satisfies("3.11.9", "3.12")
    assert not satisfies(None, "1.0")


def test_plan_machine_without_venv_needs_action():
    plan = build_plan(_rep())
    actions = [s for s in plan["steps"] if s["status"] == "action"]
    assert any(s["id"] == "venv" for s in actions)


def test_plan_empty_machine_flags_missing():
    rep = _rep(
        interpreters=[],
        gpu={"present": False},
        webview2={"present": False},
        packages={},
        torch_cuda={"installed": False},
        selected_python=None,
    )
    plan = build_plan(rep)
    by_id = {s["id"]: s for s in plan["steps"]}
    assert by_id["python"]["status"] == "action"
    assert by_id["webview2"]["status"] == "action"
    assert by_id["cuda"]["status"] == "warn"


def test_torch_cmd_picks_index_by_branch():
    gpu_cmd = " ".join(ex.torch_install_cmd("py.exe", True))
    cpu_cmd = " ".join(ex.torch_install_cmd("py.exe", False))
    assert "cu128" in gpu_cmd
    assert "/whl/cpu" in cpu_cmd


def test_ayt_cmd_mirror_and_spec():
    cmd = ex.ayt_install_cmd("py.exe", "", True)
    joined = " ".join(cmd)
    assert "tuna.tsinghua.edu.cn" in joined
    assert ex.AYT_SPEC in cmd
    # 指定 wheel 时优先 wheel 路径
    cmd_wheel = ex.ayt_install_cmd("py.exe", "D:/a.whl", False)
    assert cmd_wheel[-1] == "D:/a.whl"


def test_build_actions_sequence(tmp_path):
    acts = ex.build_actions(_rep(), ex.InstallOptions(install_dir=tmp_path))
    ids = [a["id"] for a in acts]
    assert ids[:3] == ["venv", "pip", "torch"]
    assert "ayt" in ids and "shortcut" in ids
    venv_act = next(a for a in acts if a["id"] == "venv")
    assert "venv" in venv_act["cmd"] and str(tmp_path) in venv_act["cmd"][-1]


def test_build_actions_reuse_skips_install(tmp_path):
    acts = ex.build_actions(_rep(), ex.InstallOptions(install_dir=tmp_path, mode="reuse"))
    ids = [a["id"] for a in acts]
    assert ids[0] == "reuse"
    assert "venv" not in ids and "torch" not in ids


def test_run_actions_dry_run_never_executes(tmp_path):
    acts = ex.build_actions(_rep(), ex.InstallOptions(install_dir=tmp_path))
    results = ex.run_actions(acts, install_dir=tmp_path, dry_run=True)
    assert all(r["ok"] and r.get("dry_run") for r in results)
