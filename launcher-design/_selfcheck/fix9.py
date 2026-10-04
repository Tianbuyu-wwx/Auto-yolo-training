# -*- coding: utf-8 -*-
"""fix9：排印细修（断行/平衡/字距/行高/数字特性）"""
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

# 1) 断行底线 + 禁合成
rep("  -webkit-font-smoothing:antialiased;\n  overflow:hidden;",
    "  -webkit-font-smoothing:antialiased;\n  line-break:strict;          /* 中文避头尾 */\n  font-synthesis:none;        /* 禁合成斜体/真假粗 */\n  overflow:hidden;", 1, "body-break")

# 2) 中文标签字距收敛（≤0.08em；全大写西文小标签保留大字距）
rep("letter-spacing:.12em", "letter-spacing:.08em", 1, "rline-08")
rep(".kv .k{ font-size:12px; letter-spacing:.08em;", ".kv .k{ font-size:12px; letter-spacing:.05em;", 1, "kvk-05")
rep("text-align:left; font-size:12px; letter-spacing:.08em; text-transform:uppercase;",
    "text-align:left; font-size:12px; letter-spacing:.05em; text-transform:uppercase;", 1, "th-05")
rep(".inst .il{ font-size:12px; letter-spacing:.1em;", ".inst .il{ font-size:12px; letter-spacing:.06em;", 1, "il-06")
rep(".pl-cap .a{ font-size:12px; letter-spacing:.1em;", ".pl-cap .a{ font-size:12px; letter-spacing:.06em;", 1, "plcap-06")
rep(".tcard .tm .k{ font-size:12px; letter-spacing:.08em;", ".tcard .tm .k{ font-size:12px; letter-spacing:.05em;", 1, "tck-05")

# 3) 中文多行行高抬升
rep(".sl .sd{ margin-top:3px; font-size:12px; color:var(--ink3); line-height:1.55; }",
    ".sl .sd{ margin-top:3px; font-size:12px; color:var(--ink3); line-height:1.65; }", 1, "sd-lh")
rep(".toast .tm2{ margin-top:3px; font-size:12px; color:var(--ink3); line-height:1.55; overflow-wrap:anywhere; }",
    ".toast .tm2{ margin-top:3px; font-size:12px; color:var(--ink3); line-height:1.65; overflow-wrap:anywhere; }", 1, "tm2-lh")

# 4) text-wrap / 数字特性 / 悬挂标点（Safari 支持）
rep("/* __CSS_MORE__ */",
'''/* ---------- 排印细节（text-wrap / 数字 / 标点） ---------- */
.ph-t,.mh-t,.wz-t,.modal .mt,.dropin .t,.lm-word,.tcard .tw{ text-wrap:balance; }
.lm-desc,.sd,.note,.inst-note,.pl-note,.tm2,.md,.wz-s,.devopt .dd,.svc-note,.empty .d,.pl-cap .b,.edetail .d,.lm-err .d,.dropin .d,.qs .note,.ph-s{ text-wrap:pretty; }
.mono,.inst .iv,.kv .v,.wcheck .vl,.tbl .num{ font-variant-numeric:tabular-nums slashed-zero; }
.pl-cap .b,.wz-s,.lm-desc{ hanging-punctuation:first allow-end; }

/* __CSS_MORE__ */''', 1, "typo-block")

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("OK fix9 applied")
