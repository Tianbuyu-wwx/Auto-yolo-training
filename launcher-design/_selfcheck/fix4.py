# -*- coding: utf-8 -*-
"""第四轮微调：表格名去内联覆盖（→13px）、chip/mchip/环境行值升 13px（主字号占比）"""
import io, sys

p = "AYT-Launcher-v1.html"
s = io.open(p, encoding="utf-8", newline="").read()
log = []

def rep(old, new, expect=None, tag=""):
    global s
    n = s.count(old)
    if expect is not None and n != expect:
        print("ABORT [%s] count=%d expected=%d" % (tag, n, expect))
        sys.exit(1)
    s = s.replace(old, new)
    log.append((n, tag or old[:50]))

# 1) 表格运行名列：去掉内联 12px（继承 td 的 13px）
rep(' style="font-size:12px"', '', 18, "inline-12x18")

# 2) chip 12 -> 13
rep("border:1px solid var(--line2); color:var(--ink2);\n  font-size:12px; letter-spacing:.02em; white-space:nowrap;",
    "border:1px solid var(--line2); color:var(--ink2);\n  font-size:13px; letter-spacing:.02em; white-space:nowrap;",
    1, "chip-13")

# 3) mchip 12 -> 13
rep("border:1px solid var(--line2); background:rgba(255,244,225,.02);\n  font-family:var(--f-mono); font-size:12px; color:var(--ink2); cursor:pointer;",
    "border:1px solid var(--line2); background:rgba(255,244,225,.02);\n  font-family:var(--f-mono); font-size:13px; color:var(--ink2); cursor:pointer;",
    1, "mchip-13")

# 4) 环境行：实测值 / 判定 -> 13
rep(".erow .ev{ font-family:var(--f-mono); font-size:12px; color:var(--ink2); font-variant-numeric:tabular-nums;",
    ".erow .ev{ font-family:var(--f-mono); font-size:13px; color:var(--ink2); font-variant-numeric:tabular-nums;",
    1, "erow-ev-13")
rep(".erow .er{ font-size:12px; color:var(--ink3); }",
    ".erow .er{ font-size:13px; color:var(--ink3); }", 1, "erow-er-13")

io.open(p, "w", encoding="utf-8", newline="").write(s)
for n, t in log:
    print("%3d  %s" % (n, t))
print("OK fix4 applied")
