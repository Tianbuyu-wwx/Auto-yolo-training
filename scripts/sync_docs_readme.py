#!/usr/bin/env python
"""从仓库根 README.md 生成 MkDocs 站点首页 docs/README.md。

为什么需要它：docs/README.md 是**站点首页**（mkdocs.yml 的 `nav: 首页: README.md`），
而根 README.md 是 **GitHub 首页** —— 内容必须一致，但链接写法**必须不同**：

| 场景 | 根 README（GitHub） | 站点首页（MkDocs） |
|---|---|---|
| 目录内文档 | `docs/quickstart.md` | `quickstart.md` |
| 仓库文件（LICENSE / Dockerfile / 源码） | `LICENSE` | 指向 GitHub 的绝对 URL |
| 页内锚点徽章 | `#测试` | 锚点由 MkDocs 生成、链接不可靠 → 去掉链接只留徽章图 |

手工维护两份必然漂移（实测差 147 行、整段「Web 控制台」章节缺失、测试数停在 275）。
所以改成**生成**：本脚本可重复运行，改完根 README 重跑一次即可；`--check` 模式供
CI 与 `test/test_docs_consistency.py` 断言「磁盘上的站点首页与生成结果一致」。

用法：
    python scripts/sync_docs_readme.py            # 生成 / 更新 docs/README.md
    python scripts/sync_docs_readme.py --check    # 只校验同步状态（不同步则退出码 1）
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT / "README.md"
TARGET = REPO_ROOT / "docs" / "README.md"

REPO_URL = "https://github.com/Tianbuyu-wwx/Auto-yolo-training"
BLOB_URL = f"{REPO_URL}/blob/main"

GENERATED_NOTE = (
    "<!-- 本文件由 scripts/sync_docs_readme.py 从仓库根 README.md 生成，请勿手改。\n"
    "     改完根 README 后运行：python scripts/sync_docs_readme.py -->\n"
)

# 仓库文件 → GitHub 绝对地址（站点目录里没有这些文件，相对链接会是死链）
_ABSOLUTE_LINKS = {
    "LICENSE": f"{BLOB_URL}/LICENSE",
    "Dockerfile": f"{BLOB_URL}/Dockerfile",
    "src/model_catalog.py": f"{BLOB_URL}/src/model_catalog.py",
}


def render(source_text: str) -> str:
    """把根 README 的正文渲染成站点首页（纯函数，供测试直接调用）。"""
    text = source_text.replace("\r\n", "\n")

    # 1) 页内锚点链接（徽章）：站点里的锚点由 MkDocs 生成，去掉链接层只留图片
    text = re.sub(r"\[(!\[[^\]]*\]\([^)]*\))\]\(#[^)]*\)", r"\1", text)

    # 2) 目录内文档链接：站点根目录就是 docs/，去掉前缀
    text = re.sub(r"\]\(docs/([^)]+)\)", r"](\1)", text)

    # 3) 仓库文件链接：改成 GitHub 绝对地址
    for relative, url in _ABSOLUTE_LINKS.items():
        text = text.replace(f"]({relative})", f"]({url})")

    return GENERATED_NOTE + text


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 / 校验站点首页 docs/README.md")
    parser.add_argument("--check", action="store_true", help="只校验是否与 README.md 同步")
    args = parser.parse_args()

    expected = render(SOURCE.read_text(encoding="utf-8"))

    if args.check:
        actual = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if actual.replace("\r\n", "\n") != expected:
            print("docs/README.md 与根 README.md 不同步。")
            print("修复：python scripts/sync_docs_readme.py")
            return 1
        print("docs/README.md 与根 README.md 同步 ✓")
        return 0

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    with TARGET.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(expected)
    print(f"已生成 {TARGET.relative_to(REPO_ROOT)}（源：{SOURCE.name}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
