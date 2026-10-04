# -*- coding: utf-8 -*-
"""生成 AYT-Launcher-v3.html ——「绘世式」工作台门面
参考机制（详 _ref/aaaki-huishi-dissection.md）：
  图标窄栏导航 / Hero 横幅 + 快捷卡 / 右侧状态栏 + 一键启动 /
  控制台黑底日志 / 设置行（图标+标题+副标+右控件）/ 新手-专家双模式 / 数据表格
保留：v2 的 token 主题系统（深/浅 × 4 强调色）、弹层/Toast 组件、离线字体
"""
import io

SRC = "AYT-Launcher-v2.html"
DST = "AYT-Launcher-v3.html"
s = io.open(SRC, encoding="utf-8").read()

# ---------- 从 v2 提取已验证区块 ----------
pre_a = s.index("<script>/* 主题预置"); pre_b = s.index("</script>", pre_a) + len("</script>")
PREPAINT = s[pre_a:pre_b]

tok_a = s.index(":root{", s.index("<style>"))
tok_m = ":root{ --acc-dim: rgba(var(--acc-rgb),.16); }"
tok_b = s.index(tok_m) + len(tok_m)
TOKENS = s[tok_a:tok_b]

win_a = s.index(".desk{")
win_m = "to{ opacity:1; transform:none } }"
win_b = s.index(win_m, win_a) + len(win_m)
WINSTAGE = s[win_a:win_b]

pop_a = s.index(".pop{")
pop_m = ".pop-sep{ height:1px; background:var(--line); margin:6px 8px; }"
pop_b = s.index(pop_m, pop_a) + len(pop_m)
POPS = s[pop_a:pop_b]

th_a = s.rindex("/* ===", 0, s.index("§T 外观 / 主题控件"))
th_m = "@media (prefers-reduced-motion: reduce){ html.theming, html.theming *{ transition:none !important; } }"
th_b = s.index(th_m, th_a) + len(th_m)
THEMECSS = s[th_a:th_b]

to_a = s.index(".toasts{"); to_m = ".toast .x{ flex-shrink:0; }"
to_b = s.index(to_m, to_a) + len(to_m)
TOASTS = s[to_a:to_b]

tj_a = s.index("/* ---------- 主题系统 ---------- */")
tj_m = "applyTheme(false);"
tj_b = s.index(tj_m, tj_a) + len(tj_m)
THEMEJS = s[tj_a:tj_b]

for n, b in [("PREPAINT", PREPAINT), ("TOKENS", TOKENS), ("WINSTAGE", WINSTAGE),
             ("POPS", POPS), ("THEMECSS", THEMECSS), ("TOASTS", TOASTS), ("THEMEJS", THEMEJS)]:
    print("%-9s %5d chars" % (n, len(b)))

T = io.open("_selfcheck/v3_TEMPLATE.html", encoding="utf-8").read()
out = (T.replace("@@PREPAINT@@", PREPAINT).replace("@@TOKENS@@", TOKENS)
        .replace("@@WINSTAGE@@", WINSTAGE).replace("@@POPS@@", POPS)
        .replace("@@THEMECSS@@", THEMECSS).replace("@@TOASTS@@", TOASTS)
        .replace("@@THEMEJS@@", THEMEJS))
io.open(DST, "w", encoding="utf-8", newline="").write(out)
print("written %s · %d chars · %d lines" % (DST, len(out), out.count("\n") + 1))
