# -*- coding: utf-8 -*-
"""AYT 启动器原型：探针问题批量修正（带计数断言，任何不匹配立即中止）"""
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

# ---------- 字号归一（11 / 12 / 13 / 14 / 16 / 26 / 30） ----------
rep(".ph-s{ margin-top:6px; font-size:12.5px;", ".ph-s{ margin-top:6px; font-size:13px;", 1, "ph-s->13")
rep(".tbl td.num, .tbl th.num{ text-align:right; font-family:var(--f-mono); font-size:12.5px;",
    ".tbl td.num, .tbl th.num{ text-align:right; font-family:var(--f-mono); font-size:13px;", 1, "tdnum->13")
rep("font-size:12.5px", "font-size:12px", 6, "12.5->12")
rep("font-size:11.5px", "font-size:12px", 17, "11.5->12")
rep("font-size:10.5px", "font-size:11px", 7, "10.5->11")
rep(".st .mt{ font-family:var(--f-mono); font-size:10px; color:rgba(151,137,122,.7); }",
    ".st .mt{ font-family:var(--f-mono); font-size:11px; color:var(--ink3); }", 1, "st.mt->11+ink3")
rep("font-size:10px", "font-size:11px", 3, "10->11")
rep("font-size:13.5px", "font-size:14px", 3, "13.5->14")
rep("font-size:31px", "font-size:30px", 2, "31->30")
rep(".verdict .vt{ font-family:var(--f-serif); font-size:22px; }",
    ".verdict .vt{ font-family:var(--f-serif); font-size:26px; }", 1, "vt->26")
rep(".dropin .t{ margin-top:14px; font-family:var(--f-serif); font-size:22px; }",
    ".dropin .t{ margin-top:14px; font-family:var(--f-serif); font-size:26px; }", 1, "dropin->26")
rep(".modal .mt{ font-family:var(--f-serif); font-size:21px; }",
    ".modal .mt{ font-family:var(--f-serif); font-size:26px; }", 1, "modal->26")
rep(".fam-h .fn{ font-family:var(--f-serif); font-size:17px; }",
    ".fam-h .fn{ font-family:var(--f-serif); font-size:16px; }", 1, "fam->16")
rep('style="font-size:18px;color:var(--ink3)"', 'style="font-size:16px;color:var(--ink3)"', 1, "inline->16")

# ---------- 圆角归一（0 / 10 / 999） ----------
rep("--r-lg: 16px;", "--r-lg: 10px;", 1, "r-lg")
rep("--r-sm: 6px;", "--r-sm: 10px;", 1, "r-sm")
rep("border-radius:12px", "border-radius:10px", 4, "12->10")
rep("border-radius:8px", "border-radius:10px", 3, "8->10")
rep("border-radius:7px", "border-radius:10px", 2, "7->10")
rep("border-radius:50%", "border-radius:999px", 2, "50->999")
rep("width:3px; height:14px; border-radius:2px;", "width:3px; height:14px; border-radius:999px;", 1, "navmark->999")
rep("width:6px; height:6px; border-radius:1.5px;", "width:6px; height:6px; border-radius:0;", 1, "led->0")
rep("padding:1px 5px; border-radius:4px;", "padding:1px 5px; border-radius:0;", 1, "kbd->0")
rep("width:6px; height:10px; border-radius:1px;", "width:6px; height:10px; border-radius:0;", 1, "meter->0")
rep(".mini i{ width:9px; height:4px; border-radius:1px;", ".mini i{ width:9px; height:4px; border-radius:0;", 1, "mini->0")
rep("outline-offset:2px; border-radius:4px; }", "outline-offset:2px; }", 1, "focus")
rep(".seq-track{ height:2px; border-radius:2px;", ".seq-track{ height:2px; border-radius:999px;", 1, "seqtrack->999")
rep(".epochbar{ height:4px; border-radius:2px;", ".epochbar{ height:4px; border-radius:999px;", 1, "epochbar->999")
rep(".mchip .pbar{ width:34px; height:3px; border-radius:2px;", ".mchip .pbar{ width:34px; height:3px; border-radius:999px;", 1, "pbar->999")
rep(".st .lamp{ width:9px; height:9px; border-radius:2px;", ".st .lamp{ width:9px; height:9px; border-radius:0;", 1, "lamp->0")
rep(".wz-steps .d{ width:7px; height:7px; border-radius:2px;", ".wz-steps .d{ width:7px; height:7px; border-radius:0;", 1, "wzd->0")

# ---------- 渐变扁平化（保留：桌面背景 / 窗口受光 / 鎏金按钮） ----------
rep("background:linear-gradient(180deg, rgba(255,244,225,.018), transparent);",
    "background:rgba(255,244,225,.012);", 1, "tbar")
rep("background:linear-gradient(180deg, rgba(255,244,225,.014), transparent 40%);",
    "background:rgba(255,244,225,.01);", 1, "rail")
rep("color:var(--ink); background:linear-gradient(180deg, rgba(255,244,225,.055), rgba(255,244,225,.028));",
    "color:var(--ink); background:rgba(255,244,225,.05);", 1, "rn.on")
rep("background:linear-gradient(180deg, rgba(201,163,92,.28), rgba(201,163,92,.18));",
    "background:rgba(201,163,92,.26);", 1, "switch")
rep("background:linear-gradient(90deg, var(--brass-lo), var(--brass-hi));",
    "background:var(--brass);", 2, "bars->solid")
rep("background:linear-gradient(180deg, rgba(201,163,92,.08), rgba(201,163,92,.03));",
    "background:rgba(201,163,92,.06);", 1, "mchip")
rep("background:linear-gradient(180deg, #241f19, #1c1814);", "background:#241f19;", 1, "toast")
rep("background:linear-gradient(180deg, #251f1a, #1d1915);", "background:#251f1a;", 1, "pop")
rep("background:linear-gradient(180deg, #27211b, #1e1a16);", "background:#27211b;", 1, "ctx")
rep("width:430px; background:linear-gradient(180deg, #262019, #1d1915);",
    "width:430px; background:#231e19;", 1, "modal")
rep("background:linear-gradient(180deg, rgba(201,163,92,.1), rgba(201,163,92,.03));",
    "background:rgba(201,163,92,.07);", 1, "devopt")
rep("background:linear-gradient(180deg, rgba(201,106,92,.1), rgba(201,106,92,.05));",
    "background:rgba(201,106,92,.07);", 1, "lmerr")
rep("background:linear-gradient(180deg, rgba(201,163,92,.07), rgba(201,163,92,.02)); }",
    "background:rgba(201,163,92,.05); }", 1, "dropin")
rep("""  background:
    radial-gradient(900px 500px at 24% -10%, rgba(255,236,206,.05), transparent 60%),
    linear-gradient(180deg, #14120f, #100e0c);""",
    "  background:#13110e;", 1, "wizard")

# ---------- 对比度 ----------
rep(".logs .ln .ts{ color:rgba(151,137,122,.65); flex-shrink:0; }",
    ".logs .ln .ts{ color:var(--ink3); flex-shrink:0; }", 1, "ts->ink3")

io.open(p, "w", encoding="utf-8", newline="").write(s)
for n, t in log:
    print("%3d  %s" % (n, t))
print("OK, all edits applied")
