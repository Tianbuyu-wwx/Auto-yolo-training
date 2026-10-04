# -*- coding: utf-8 -*-
"""第五轮微调：小按钮/说明文字 12 -> 13（主字号占比收口，按钮字号全系统一为 13）"""
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

rep(".btn.sm{ height:28px; padding:0 11px; font-size:12px; border-radius:var(--r-sm); }",
    ".btn.sm{ height:28px; padding:0 11px; font-size:13px; border-radius:var(--r-sm); }", 1, "btn.sm-13")
rep(".btn.xs{ height:24px; padding:0 9px; font-size:12px; border-radius:var(--r-sm); gap:6px; }",
    ".btn.xs{ height:24px; padding:0 9px; font-size:13px; border-radius:var(--r-sm); gap:6px; }", 1, "btn.xs-13")
rep("font-size:12px; color:var(--ink3); line-height:1.65; display:flex; gap:8px; align-items:flex-start; }",
    "font-size:13px; color:var(--ink3); line-height:1.65; display:flex; gap:8px; align-items:flex-start; }", 1, "svc-note-13")
rep(".tab-cap{ margin:4px 0 14px; font-size:12px; color:var(--ink3);",
    ".tab-cap{ margin:4px 0 14px; font-size:13px; color:var(--ink3);", 1, "tab-cap-13")
rep('<span class="issue" style="color:var(--warn);font-size:12px">',
    '<span class="issue" style="color:var(--warn)">', 1, "issue-inline")

io.open(p, "w", encoding="utf-8", newline="").write(s)
for n, t in log:
    print("%3d  %s" % (n, t))
print("OK fix5 applied")
