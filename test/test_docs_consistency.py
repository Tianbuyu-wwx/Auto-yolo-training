"""文档一致性守卫：站点首页与根 README 同步、README 里的可机检数字与实际一致。

## 为什么需要它

2026-09-17 的审计发现文档层是**系统性滞后**而不是个别笔误：

- `docs/README.md`（MkDocs 站点首页）是 Gradio 时代的手抄副本，与根 README 差 147 行，
  整段「Web 控制台」章节缺失、测试数停在 275；
- 根 README 自己就自相矛盾：徽章写 275、功能表写 300，而实际是 344；
- 页面数写 6，实际 7。

这类漂移靠人眼 review 靠不住（数字分散在徽章、表格、命令说明四处），所以把**可机检的部分**
固化成断言：站点首页必须等于生成器的输出、README 里的测试数与页面数必须等于实测量。

数字改了却忘了改文档 → 这里红；文档改了数字写错 → 这里也红。
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "README.md"
DOCS_README = REPO_ROOT / "docs" / "README.md"
PAGES_DIR = REPO_ROOT / "frontend" / "src" / "pages"

sys.path.insert(0, str(REPO_ROOT / "scripts"))

import sync_docs_readme  # noqa: E402  （先加 path 再导入）


# ----------------------------------------------------------------------
# 1. 站点首页 == 由根 README 生成的结果
# ----------------------------------------------------------------------
def test_docs_readme_is_in_sync_with_root_readme() -> None:
    """docs/README.md 必须等于生成器输出（改根 README 后要重跑同步脚本）"""
    expected = sync_docs_readme.render(README.read_text(encoding="utf-8"))
    actual = DOCS_README.read_text(encoding="utf-8")
    assert actual.replace("\r\n", "\n") == expected, (
        "docs/README.md 与根 README.md 不同步。\n"
        "修复：python scripts/sync_docs_readme.py"
    )


# ----------------------------------------------------------------------
# 2. README 里的测试数字 == 测试套件实际收集到的数量
# ----------------------------------------------------------------------
def _collected_test_count() -> int:
    """按 README 记载的同一条命令收集测试（`-m "not gpu and not training"`）

    注意 pytest 的两种输出形态：标记全选时是 ``372 tests collected``，一旦有被标记
    排除的用例就变成 ``358/361 tests collected (3 deselected)`` —— 要取斜杠**前面**
    那个数（本命令实际会跑的规模），取后面会把 GPU 用例也算进「CPU-safe 套件」。
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "test/", "--collect-only", "-q",
         "-m", "not gpu and not training", "-p", "no:cacheprovider"],
        cwd=REPO_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=300,
    )
    match = re.search(r"(\d+)(?:/\d+)?\s+tests?\s+collected", result.stdout)
    if match is None:
        pytest.fail(f"无法从 pytest --collect-only 输出里解析收集数量：\n{result.stdout[-800:]}")
    return int(match.group(1))


def test_readme_numbers_match_the_suite() -> None:
    """README 宣称的「N passed, M skipped」必须与套件实际收集数一致，且四处数字互相一致"""
    readme = README.read_text(encoding="utf-8")

    stats = re.search(r"(\d+)\s*passed,\s*(\d+)\s*skipped", readme)
    assert stats, "README 里找不到「N passed, M skipped」这一行（测试统计的权威数字）"
    passed, skipped = int(stats.group(1)), int(stats.group(2))

    collected = _collected_test_count()
    assert passed + skipped == collected, (
        f"README 写 {passed} passed + {skipped} skipped = {passed + skipped}，"
        f"但套件实际收集到 {collected} 个测试。改测试后请同步 README。"
    )

    # 徽章是 shields.io 的 "tests passed" 徽章 → 必须等于 passed；
    # 「跑测试套件（N tests）」描述的是那条命令会收集到多少个用例 → passed + skipped
    # （= collected）同样是真实值，两者都接受，但不接受任何过期数字。
    badge = re.search(r"tests-(\d+)%20passed", readme)
    if badge:
        assert int(badge.group(1)) == passed, (
            f"徽章写的是 tests-{badge.group(1)}，权威的 passed 数是 {passed}"
        )

    documented: dict[str, int] = {}
    for match in re.finditer(r"（(\d+) tests）", readme):
        documented[f"命令说明（{match.group(1)} tests）"] = int(match.group(1))

    assert documented, "README 里一个可机检的测试数字都没找到（守卫形同虚设）"
    wrong = {label: value for label, value in documented.items() if value not in {passed, collected}}
    assert not wrong, (
        f"这些位置写的测试数与权威数字（{passed} passed / {collected} collected）不一致："
        + "；".join(f"{label} → {value}" for label, value in wrong.items())
    )

    # 文档索引页同样宣称当前测试数 —— 一起守。
    # 注意**不含** docs/第一阶段可信基线实施记录与后续方案.md：那是 2026-07-22 的历史
    # 快照（92 passed），把它改成今天的数字反而是篡改历史记录。
    about = (REPO_ROOT / "docs" / "about.md").read_text(encoding="utf-8")
    about_stats = re.search(r"(\d+)\s*passed\s*/\s*(\d+)\s*skipped", about)
    assert about_stats, "docs/about.md 里的测试统计格式变了（守卫需要更新）"
    assert (int(about_stats.group(1)), int(about_stats.group(2))) == (passed, skipped), (
        f"docs/about.md 写的是 {about_stats.group(1)} passed / {about_stats.group(2)} skipped，"
        f"权威数字是 {passed} passed / {skipped} skipped"
    )


# ----------------------------------------------------------------------
# 3. README / 控制台文档里的页面数 == frontend 实际页面数
# ----------------------------------------------------------------------
def test_documented_page_count_matches_frontend() -> None:
    """README 与 console.md 宣称的页面数必须等于 frontend/src/pages 下的实际页面数"""
    pages = [p for p in PAGES_DIR.glob("*.vue") if p.name != "NotFoundPage.vue"]
    assert pages, f"在 {PAGES_DIR} 下没找到页面组件"

    for path in (README, REPO_ROOT / "docs" / "console.md"):
        text = path.read_text(encoding="utf-8")
        claimed = {int(m.group(1)) for m in re.finditer(r"(\d+) 个页面", text)}
        assert claimed, f"{path.name} 里没写「N 个页面」"
        assert claimed == {len(pages)}, (
            f"{path.name} 写的页面数 {claimed} 与实际 {len(pages)} 个（{sorted(p.stem for p in pages)}）不符"
        )
