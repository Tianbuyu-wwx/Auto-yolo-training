# -*- coding: utf-8 -*-
"""生成 AYT-Launcher-v5.html —— 液态玻璃主题（Liquid Glass，默认皮肤）

视觉源：InternalBeyond 欢迎页（冰雾玻璃 / 水面涟漪 / 顶部柔光 / 重暗角）；
动效规范：motion-web（三层时长 / expo 缓动 / 反 AI 味闸门）；
结构：存续 v4（方向 D 融合：九页 + 六场景）。
与 gen_v4 同构：从已验收的 AYT-Launcher-v4.html 提取公共区块注入 v5_TEMPLATE。
"""
import io
import re

SRC = "AYT-Launcher-v4.html"
DST = "AYT-Launcher-v5.html"
s = io.open(SRC, encoding="utf-8").read()

# ---------- 从 v4 提取已验证区块 ----------
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

T = io.open("_selfcheck/v5_TEMPLATE.html", encoding="utf-8").read()
out = (T.replace("@@PREPAINT@@", PREPAINT).replace("@@TOKENS@@", TOKENS)
        .replace("@@WINSTAGE@@", WINSTAGE).replace("@@POPS@@", POPS)
        .replace("@@THEMECSS@@", THEMECSS).replace("@@TOASTS@@", TOASTS)
        .replace("@@THEMEJS@@", THEMEJS))
left = re.findall(r"@@[A-Z]+@@", out)
assert not left, "unreplaced placeholders: %s" % left

io.open(DST, "w", encoding="utf-8", newline="").write(out)
print("written %s · %d chars · %d lines" % (DST, len(out), out.count("\n") + 1))
