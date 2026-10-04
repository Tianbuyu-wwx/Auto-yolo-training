# -*- coding: utf-8 -*-
"""fix7：浅色模式对比度修正 + 最后一批硬编码黑/白发的 token 化"""
import io, sys

P = "AYT-Launcher-v1.html"
s = io.open(P, encoding="utf-8", newline="").read()

def rep(old, new, expect, tag):
    global s
    n = s.count(old)
    if n != expect:
        print("ABORT [%s] count=%d expected=%d" % (tag, n, expect)); sys.exit(1)
    s = s.replace(old, new)
    print("  %d  %s" % (n, tag))

# 1) inset token 定义（深/浅各一组）
rep("  --scrim:     rgba(8,6,5,.66);",
    "  --scrim:     rgba(8,6,5,.66);\n  --inset-1:   rgba(0,0,0,.22);       /* 分段控件槽等凹陷 */\n  --inset-2:   rgba(0,0,0,.16);       /* 仪表列等压暗面板 */", 1, "inset-tokens-dark")
rep("  --scrim:     rgba(74,58,38,.32);",
    "  --scrim:     rgba(74,58,38,.32);\n  --inset-1:   rgba(var(--lift-rgb),.09);\n  --inset-2:   rgba(var(--lift-rgb),.05);", 1, "inset-tokens-light")

# 2) 两处黑影 token 化
rep(".seg{ display:inline-flex; border:1px solid var(--line2); border-radius:var(--r); overflow:hidden; padding:2px; gap:2px; background:rgba(0,0,0,.22); }",
    ".seg{ display:inline-flex; border:1px solid var(--line2); border-radius:var(--r); overflow:hidden; padding:2px; gap:2px; background:var(--inset-1); }", 1, "seg-inset")
rep("  border-left:1px solid var(--line); background:rgba(0,0,0,.16);",
    "  border-left:1px solid var(--line); background:var(--inset-2);", 1, "lmright-inset")

# 3) 244,236,222 系发丝线 → lift token（tokens 内的 --line/--line2 保持原样）
rep("rgba(244,236,222,.05)",  "rgba(var(--lift-rgb),.05)", 1, "hair-05")
rep("rgba(244,236,222,.12)",  "rgba(var(--lift-rgb),.12)", 2, "hair-12")
rep("rgba(244,236,222,.055)", "rgba(var(--lift-rgb),.055)", 1, "hair-055")
rep("rgba(244,236,222,.22)",  "rgba(var(--lift-rgb),.22)", 1, "hair-22")

# 4) 浅色对比度修正（用求解器定的值）
rep("--ink3:      #7f7362;", "--ink3:      #6d6252;", 1, "light-ink3")
rep("--acc-lo:#8a6a2c; --acc-text:#7f5f1a;", "--acc-lo:#8a6a2c; --acc-text:#775a18;", 1, "light-brass-text")
rep("--acc-lo:#35604b; --acc-text:#3f7259;", "--acc-lo:#35604b; --acc-text:#3a6b53;", 1, "light-celadon-text")

# 5) 残留自检
left = {
  "rgba(0,0,0,": len([m for m in s.split("rgba(0,0,0,")[1:]]),
  "rgba(244,236,222,": len([m for m in s.split("rgba(244,236,222,")[1:]]),
}
print("残留 rgba(0,0,0,   =", left["rgba(0,0,0,"], "(应为 6：vignette/win-shadow×3/input-inset/sh-float×2 = 7? 见下)")
print("残留 rgba(244,236,222, =", left["rgba(244,236,222,"], "(应为 2 = --line/--line2)")
io.open(P, "w", encoding="utf-8", newline="").write(s)
print("OK fix7 applied")
