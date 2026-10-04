# -*- coding: utf-8 -*-
"""fix11：首页底部「最近训练 / 快速开始」对齐
- 修 16px 顶偏移（.mod+.mod 堆叠规则误伤网格并排）
- 两侧内边距统一（去左侧 inline padding）
- 标题行高统一（网格内 .mod-head min-height:24px，局部作用域）
- 等高（去除 align-items:start → 默认 stretch）
"""
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

# 1) 网格内并排模块不受「垂直堆叠间距」影响
rep(".mod + .mod{ margin-top:16px; }",
    ".mod + .mod{ margin-top:16px; }\n.grid2 > .mod + .mod{ margin-top:0; }   /* 网格内并排时不受相邻堆叠规则影响 */", 1, "sibling-guard")

# 2) 网格内标题行统一高度（局部作用域，避免影响其它屏）
rep(".mod-head{ display:flex; align-items:center; gap:12px; margin-bottom:16px; }",
    ".mod-head{ display:flex; align-items:center; gap:12px; margin-bottom:16px; }\n.grid2 .mod-head{ min-height:24px; }", 1, "head-minheight")

# 3) 等高：去掉 align-items:start（默认 stretch，两块同高、底边齐）
rep(".grid2{ display:grid; grid-template-columns:minmax(0,7fr) minmax(0,5fr); gap:16px; align-items:start; }",
    ".grid2{ display:grid; grid-template-columns:minmax(0,7fr) minmax(0,5fr); gap:16px; }", 1, "grid-stretch")

# 4) 左侧模块内边距与右侧统一（去 inline padding，回落 .mod 的 22px）
rep('<div class="mod" style="padding:18px 20px 10px">', '<div class="mod">', 1, "padding-unify")

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("OK fix11 applied")
