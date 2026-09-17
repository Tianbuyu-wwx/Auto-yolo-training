"""
依赖声明完整性：`src/` 里**无条件导入**的每个第三方包，都必须写在 requirements.txt 里。

## 为什么要这个测试

2026-09-16，CI 的 tests 全红，12 个测试统一挂在
`ModuleNotFoundError: No module named 'pydantic_settings'`。

`src/settings.py:27` 需要的是 **`pydantic-settings`**，而三处依赖声明
（requirements.txt / pyproject.toml / constraints.txt）里写的是 **`pydantic`** ——
两个包名字只差一个后缀，import 名（`pydantic_settings`）与发行名
（`pydantic-settings`）又不一致，人工审 requirements.txt 基本看不出来。

本地一直全绿，只是因为这台机器恰好装过它。而那个导入点在
`config_generator.generate_training_config()` 里，是**每次训练的必经阶段** ——
也就是说按文档全新安装后一次训练都跑不起来，Docker 镜像（同一个 requirements 链）同样中招。

## 判定口径

- 只扫 `src/`，只看 `level == 0` 的导入（相对导入是项目内部）
- 位于 `try:` 内的导入**视为可选依赖**，不要求出现在 requirements.txt
  （如 `pycocotools`、`tensorboard` —— 缺了只降级功能，不阻断主流程）
- 其余（含函数体内的）无条件导入必须被声明，且能映射到发行名
- **例外 `OPTIONAL_FEATURE_IMPORTS`**：整块功能本身可选（当前只有已冻结的
  Gradio 界面）的依赖，允许不在 requirements.txt 里，但必须满足两条 ——
  ① 在 pyproject 的某个 extra 里声明；② 入口给出可操作的缺依赖报错
  （`test_gradio_entry_gives_actionable_error_when_missing` 守着第 ② 条）
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import tomllib
from importlib.metadata import packages_distributions
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
REQUIREMENTS = REPO_ROOT / "requirements.txt"
PYPROJECT = REPO_ROOT / "pyproject.toml"

# 可选功能依赖：允许不在 requirements.txt 里，但必须在 pyproject 的 extra 中声明
# 且入口要有可操作的缺依赖提示。gradio 界面已冻结（控制台取代之），
# 把它留在必需依赖里等于让所有人生成 40MB+ 的安装体积去装一个不用的界面。
OPTIONAL_FEATURE_IMPORTS = {
    "gradio": "已冻结的 Gradio 界面（pyproject extra: [gradio]）",
}


def _normalize(name: str) -> str:
    """PEP 503 归一：比较时大小写与 -/_/. 都不区分"""
    return name.lower().replace("_", "-").replace(".", "-")


def _declared_distributions() -> set[str]:
    """requirements.txt 里声明的发行名（去掉 extras / 版本约束 / 选项行）"""
    declared: set[str] = set()
    for raw in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        name = line.split("[", 1)[0]
        for sep in ("==", ">=", "<=", "~=", "!=", ">", "<", ";"):
            name = name.split(sep, 1)[0]
        if name.strip():
            declared.add(_normalize(name.strip()))
    return declared


def _normalize_spec(raw: str) -> str:
    """从一条依赖声明里取出归一化后的发行名"""
    name = raw.split("[", 1)[0]
    for sep in ("==", ">=", "<=", "~=", "!=", ">", "<", ";", " "):
        name = name.split(sep, 1)[0]
    return _normalize(name.strip())


def _extra_distributions() -> set[str]:
    """pyproject 的 optional-dependencies 里声明的发行名（全部 extra 合并）"""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    extras = data.get("project", {}).get("optional-dependencies", {})
    return {
        _normalize_spec(item)
        for items in extras.values()
        for item in items
        if item.strip()
    }


def _local_top_level_names() -> set[str]:
    """仓库根下自带的顶层包/模块名（属于项目自身，不该出现在 requirements.txt）"""
    local = set()
    for child in REPO_ROOT.iterdir():
        if child.is_dir() and (child / "__init__.py").exists():
            local.add(child.name)
        elif child.is_file() and child.suffix == ".py":
            local.add(child.stem)
    return local


def _required_third_party_imports() -> dict[str, list[str]]:
    """无条件导入的第三方顶层模块 -> 出现位置（module:line）"""
    local = _local_top_level_names()
    found: dict[str, list[str]] = {}

    for path in sorted(SRC_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)

        # 收集所有被 try 包住的 import 行号 —— 这些是显式可选依赖
        guarded: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                for inner in ast.walk(node):
                    if isinstance(inner, (ast.Import, ast.ImportFrom)):
                        end = getattr(inner, "end_lineno", None) or inner.lineno
                        guarded.update(range(inner.lineno, end + 1))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules = [node.module.split(".")[0]]
            else:
                continue
            # 注意 isinstance 判定必须在前：ast.walk 会遍历到 Module 节点，它没有 lineno
            if node.lineno in guarded:
                continue
            for module in modules:
                if module in sys.stdlib_module_names or module in local:
                    continue
                where = f"{path.relative_to(REPO_ROOT)}:{node.lineno}"
                found.setdefault(module, []).append(where)

    return found


def test_required_imports_are_declared_in_requirements() -> None:
    """每个无条件导入的第三方包都必须在 requirements.txt 里有对应声明"""
    declared = _declared_distributions()
    mapping = packages_distributions()
    problems: list[str] = []

    extra_declared = _extra_distributions()

    for module, where in sorted(_required_third_party_imports().items()):
        if module in OPTIONAL_FEATURE_IMPORTS:
            dists = mapping.get(module) or []
            if not any(_normalize(d) in extra_declared for d in dists):
                problems.append(
                    f"  {module:<20} 属可选功能（{OPTIONAL_FEATURE_IMPORTS[module]}），"
                    f"但 pyproject 的 extras 里没有声明  ← {where[0]}")
            continue
        dists = mapping.get(module)
        if not dists:
            # 装不上就映射不出来：要么没声明（这个测试要抓的正是它），
            # 要么这个 import 名没有对应的发行元数据
            problems.append(
                f"  {module:<20} 无法映射到任何发行名（未安装或未声明）  ← {where[0]}")
            continue
        if not any(_normalize(d) in declared for d in dists):
            problems.append(
                f"  {module:<20} 发行名 {dists} 不在 requirements.txt  ← {where[0]}")

    if problems:
        pytest.fail(
            "以下被 src/ 无条件导入的包没有在 requirements.txt 里声明：\n"
            + "\n".join(problems)
            + "\n\n全新安装（以及按 requirements-dev.txt 构建的 Docker 镜像）会缺这些包。\n"
            "若确是可选依赖，请把 import 放进 try/except 并说明降级行为。"
        )


def test_guarded_imports_are_not_required() -> None:
    """反向保险：try 内的可选依赖不应被硬塞进必需依赖，否则等于变相强制安装"""
    declared = _declared_distributions()
    mapping = packages_distributions()
    required = set(_required_third_party_imports())

    offenders = []
    for module in ("pycocotools", "tensorboard"):
        if module in required:
            continue
        dists = mapping.get(module) or []
        hit = [d for d in dists if _normalize(d) in declared]
        if hit:
            offenders.append(f"  {module} 是 try 内可选依赖，却被声明为必需：{hit}")

    assert not offenders, "\n".join(offenders)


# ----------------------------------------------------------------------
# 可选功能：缺依赖时必须给出可操作的提示，而不是 ImportError 堆栈
# ----------------------------------------------------------------------
_GRADIO_BLOCKER = '''"""测试夹具：让 import gradio 失败，模拟未安装 [gradio] extra 的环境"""\n
import sys


class _BlockGradio:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "gradio" or fullname.startswith("gradio."):
            raise ImportError(f"No module named {fullname!r} (blocked by audit fixture)")
        return None


sys.meta_path.insert(0, _BlockGradio())
'''


def test_gradio_entry_gives_actionable_error_when_missing(tmp_path: Path) -> None:
    """没装 gradio 时 `python gradio_app.py` 要打印安装命令并以 2 退出。

    用一个 sitecustomize.py 在子进程里屏蔽 gradio —— 比"检查有没有装"更接近真实：
    验证的是**入口的兜底分支**真的会跑到。
    """
    (tmp_path / "sitecustomize.py").write_text(_GRADIO_BLOCKER, encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT), str(tmp_path)])

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "gradio_app.py")],
        cwd=REPO_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env, timeout=180,
    )
    output = (result.stdout or "") + (result.stderr or "")
    assert result.returncode == 2, f"退出码 {result.returncode}\n{output[-600:]}"
    assert "pip install" in output, output[-600:]
    assert "gradio" in output.lower()
