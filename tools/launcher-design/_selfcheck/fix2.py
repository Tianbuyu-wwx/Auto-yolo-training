# -*- coding: utf-8 -*-
"""第二轮修正：字号收敛到 5 档（12/13/16/26/30）、err 对比度、LED 辉光收缩、emoji 清除"""
import io, sys

p = "AYT-Launcher-v1.html"
s = io.open(p, encoding="utf-8", newline="").read()
log = []

def rep(old, new, expect=None, tag=""):
    global s
    n = s.count(old)
    if expect is not None and n != expect:
        print("ABORT [%s] count=%d expected=%d :: %r" % (tag, n, expect, old[:90]))
        sys.exit(1)
    s = s.replace(old, new)
    log.append((n, tag or old[:60]))

# 1) 字号：11 -> 12（30 处）、14 -> 13（6 处）
rep("font-size:11px", "font-size:12px", 30, "11->12")
rep("font-size:14px", "font-size:13px", 6, "14->13")

# 2) 对比度：err 红抬亮（文本用；rgba 描边/底色保持原样）
rep("#c96a5c", "#d2766b", None, "err->brighter")

# 3) LED 辉光收缩：仅保留「活动/失败」语义的辉光（led.live / 轨道 now / fail）
rep(".led.ok{ background:var(--ok); opacity:1; box-shadow:0 0 8px -1px rgba(143,176,126,.55); }",
    ".led.ok{ background:var(--ok); opacity:1; }", 1, "led.ok")
rep(".led.warn{ background:var(--warn); opacity:1; box-shadow:0 0 8px -1px rgba(217,154,78,.5); }",
    ".led.warn{ background:var(--warn); opacity:1; }", 1, "led.warn")
rep(".led.err{ background:var(--err); opacity:1; box-shadow:0 0 8px -1px rgba(201,106,92,.55); }",
    ".led.err{ background:var(--err); opacity:1; }", 1, "led.err")
rep(".led.brass{ background:var(--brass); opacity:1; box-shadow:0 0 9px -1px rgba(201,163,92,.65); }",
    ".led.brass{ background:var(--brass); opacity:1; }", 1, "led.brass")

# 4) emoji 清除：✓ -> 文字
rep('<span class="v">frontend/dist <span class="ok">✓</span> 已构建</span>',
    '<span class="v">frontend/dist · <span class="ok">已构建</span></span>', 1, "checkmark")

io.open(p, "w", encoding="utf-8", newline="").write(s)
for n, t in log:
    print("%3d  %s" % (n, t))
print("OK fix2 applied")
