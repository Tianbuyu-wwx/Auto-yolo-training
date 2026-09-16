#!/usr/bin/env python3
"""Docker 构建上下文预检：Dockerfile 要的路径，.dockerignore 会不会把它排掉。

**为什么需要它**：`docker build` 要到很后面才报 "excluded by .dockerignore"，
而且报的是第一个撞上的路径 —— 修一个再跑一次才发现下一个。本项目就吃过两次：
  1. `!README.md` 写在 `*.md` 之前，被重新排除 → setuptools 解析 readme 失败；
  2. `.dockerignore` 排除了 `test/`，而 Dockerfile 有 `COPY test/` → 构建失败。
这两类都能在**不启动 Docker 守护进程**的前提下静态查出来。

用法：
    python scripts/check_dockerfile_context.py [--root .]

判定口径（重要，别当成绝对）：
  .dockerignore 的完整语义由 Docker 的 Go 实现决定，本脚本用两套模型各算一遍：
    strict —— 只认「整路径」或「祖先目录」命中；
    loose  —— 额外认 .gitignore 式「无斜杠模式匹配任意层级的 basename」。
  被判 EXCLUDED 的按 strict 命中（几乎确定会失败）；只被 loose 命中的标 AT-RISK
  （是否真的失败取决于 Docker 版本对无斜杠模式的解释），由人复核。
"""
from __future__ import annotations

import argparse
import fnmatch
import re
import sys
from pathlib import Path

SOURCE_FLAGS = re.compile(r"^--[a-zA-Z-]+(=[^\s]+)?$")


def parse_dockerfile(text: str) -> list[dict]:
    """抽出所有 COPY / ADD 的源路径（含跨阶段 --from 的标记）。"""
    # 续行拼接
    joined: list[str] = []
    buf = ""
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.lstrip().startswith("#"):
            continue
        if line.endswith("\\"):
            buf += line[:-1] + " "
            continue
        joined.append(buf + line)
        buf = ""
    if buf:
        joined.append(buf)

    out = []
    for line in joined:
        parts = line.split()
        if not parts:
            continue
        instr = parts[0].upper()
        if instr not in ("COPY", "ADD"):
            continue
        from_stage = None
        i = 1
        while i < len(parts) and parts[i].startswith("--"):
            tok = parts[i]
            if tok.startswith("--from="):
                from_stage = tok.split("=", 1)[1]
            i += 1
        args = parts[i:]
        if len(args) < 2:
            continue
        srcs, dest = args[:-1], args[-1]
        if from_stage is not None:
            continue  # 跨阶段拷的是镜像内的路径，与本文件的上下文无关
        for s in srcs:
            if s.startswith("http://") or s.startswith("https://"):
                continue
            out.append({"src": s, "dest": dest, "line": line.strip()})
    return out


def load_ignore_patterns(path: Path) -> list[str]:
    pats = []
    if not path.exists():
        return pats
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        pats.append(s)
    return pats


def ancestors(rel: str) -> list[str]:
    """['a/b/c'] -> ['a', 'a/b']（不含自身）。"""
    parts = rel.split("/")[:-1]
    return ["/".join(parts[: i + 1]) for i in range(len(parts))]


def _hit(target: str, pat: str) -> bool:
    if fnmatch.fnmatchcase(target, pat):
        return True
    # 'dir' 模式也要命中 'dir' 之下的内容 —— 由 ancestors() 覆盖，
    # 这里额外处理 'dir/**' 这类写法
    return pat.endswith("/**") and fnmatch.fnmatchcase(target, pat[:-3].rstrip("/"))


def is_excluded(rel: str, pats: list[str], loose: bool) -> str | None:
    """返回命中的最后一条模式（Docker 取最后一条命中的），未命中返回 None。"""
    rel = rel.replace("\\", "/").strip("/")
    anc = ancestors(rel)
    base = rel.split("/")[-1]
    verdict = None
    for raw in pats:
        neg = raw.startswith("!")
        pat = raw[1:] if neg else raw
        anchored = pat.startswith("/")
        pat = pat.lstrip("/")
        if pat.endswith("/"):
            pat = pat.rstrip("/")
        if not pat:
            continue

        matched = _hit(rel, pat) or any(_hit(a, pat) for a in anc)
        if not matched and loose and not anchored and "/" not in pat:
            matched = fnmatch.fnmatchcase(base, pat)
        if matched:
            verdict = None if neg else raw
    return verdict


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="构建上下文根目录，默认当前目录")
    ap.add_argument("--dockerfile", default="Dockerfile")
    ap.add_argument("--ignorefile", default=".dockerignore")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    df = root / args.dockerfile
    if not df.exists():
        print(f"找不到 {df}")
        return 2

    copies = parse_dockerfile(df.read_text(encoding="utf-8"))
    pats = load_ignore_patterns(root / args.ignorefile)

    print(f"上下文根 : {root}")
    print(f"忽略规则 : {len(pats)} 条（来自 {args.ignorefile}）")
    print(f"COPY 条目: {len(copies)}\n")

    problems, at_risk, ok = [], [], 0
    for c in copies:
        src = c["src"]
        rel = src.rstrip("/").lstrip("./")
        on_disk = (root / rel).exists()
        hard = is_excluded(rel, pats, loose=False)
        soft = is_excluded(rel, pats, loose=True)

        if not on_disk:
            problems.append((rel, "源不存在", c["line"]))
            print(f"  MISSING  {rel:<34} ← {c['line']}")
            continue
        if hard:
            problems.append((rel, f"被规则 {hard!r} 排除（strict）", c["line"]))
            print(f"  EXCLUDED {rel:<34} ← 命中 {hard!r}")
            continue
        if soft:
            at_risk.append((rel, f"可能被规则 {soft!r} 排除（loose）", c["line"]))
            print(f"  AT-RISK  {rel:<34} ← 可能命中 {soft!r}")
            continue
        ok += 1
        # 目录源：统计有多少内容会被排掉（不会报错，但会拷不全）
        extra = ""
        if (root / rel).is_dir():
            files = [p for p in (root / rel).rglob("*") if p.is_file()]
            dropped = sum(1 for p in files if is_excluded(str(p.relative_to(root)), pats, loose=True))
            if dropped:
                extra = f"  （目录内 {dropped}/{len(files)} 个文件会被忽略）"
        print(f"  OK       {rel:<34}{extra}")

    print()
    print("=" * 62)
    print(f"OK {ok} / AT-RISK {len(at_risk)} / 会失败 {len(problems)}")
    if problems:
        print("\n构建必然失败或产不出想要的东西：")
        for rel, why, line in problems:
            print(f"  - {rel}: {why}\n      {line}")
    if at_risk:
        print("\n需要人工复核（取决于 Docker 对无斜杠模式的解释）：")
        for rel, why, _line in at_risk:
            print(f"  - {rel}: {why}")

    # 反向检查：把「被忽略的文件」里有没有 Dockerfile 明确需要的目录引用（如 test/）
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
