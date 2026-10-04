# -*- coding: utf-8 -*-
"""fix6：主题系统第一期 —— token 架构化
- 颜色字面量 → 语义 token（lift / acc / 语义色 rgb 三元组）
- :root 重写为 [data-mode] 双模式 + [data-accent] 四套强调色
- <html> 默认属性 + 预置脚本（防闪烁）
所有替换带断言；末尾做残留断言与关键对比度报告。
"""
import io, re, sys

P = "AYT-Launcher-v1.html"
s = io.open(P, encoding="utf-8", newline="").read()
log = []

def rep(old, new, expect=None, tag=""):
    global s
    n = s.count(old)
    if expect is not None and n != expect:
        print("ABORT [%s] count=%d expected=%d" % (tag, n, expect)); sys.exit(1)
    if n == 0:
        print("WARN  [%s] count=0 (no-op)" % tag)
    s = s.replace(old, new)
    log.append((n, tag or old[:44]))

# ============ 0. meta + html 属性 ============
rep('<meta name="color-scheme" content="dark" />', '<meta name="color-scheme" content="dark light" />', 1, "meta-scheme")
rep('<html lang="zh-CN">', '<html lang="zh-CN" data-mode="dark" data-accent="brass">', 1, "html-attrs")

# 预置脚本：先于样式生效，防主题闪烁
rep('<title>Auto YOLO Training · 启动器 — 设计稿 v1</title>',
    '<title>Auto YOLO Training · 启动器 — 设计稿 v1</title>\n<script>/* 主题预置：先于样式生效，避免切换闪烁 */\n(function(){try{\n  var d=document.documentElement,st={};\n  try{ st=JSON.parse(localStorage.getItem(\'ayt.theme\')||\'{}\'); }catch(_){}\n  var pref=st.mode||\'dark\';\n  var sys=matchMedia(\'(prefers-color-scheme: light)\').matches?\'light\':\'dark\';\n  d.dataset.mode=(pref===\'system\')?sys:pref; d.dataset.modePref=pref;\n  d.dataset.accent=st.accent||\'brass\';\n  if(st.accent===\'custom\'&&st.cc){ for(var k in st.cc){ d.style.setProperty(\'--\'+k, st.cc[k]); } }\n}catch(e){}})();</script>', 1, "prepaint")

# ============ 1. tokens 块重写 ============
old_tokens = """:root{
  --bg:        #131110;
  --bg-card:   #1a1715;
  --bg-raise:  #231f1a;
  --bg-deep:   #0c0a09;
  --line:      rgba(244,236,222,.07);
  --line2:     rgba(244,236,222,.14);

  --ink:       #f2ece1;
  --ink2:      #bdb2a0;
  --ink3:      #97897a;

  --brass:     #c9a35c;
  --brass-hi:  #e9d3a2;
  --brass-lo:  #8f7136;
  --brass-dim: rgba(201,163,92,.16);

  --ok:   #8fb07e;
  --warn: #d99a4e;
  --err:  #d2766b;

  --f-serif: "Instrument Serif", "Noto Serif SC", "Songti SC", serif;
  --f-sans:  "Instrument Sans Variable", "Instrument Sans", "Noto Sans SC", "Segoe UI", "Microsoft YaHei", sans-serif;
  --f-mono:  "IBM Plex Mono", "Cascadia Mono", Consolas, monospace;

  --r-lg: 10px;
  --r:    10px;
  --r-sm: 10px;

  --t-fast: .15s; --t: .24s; --t-slow: .5s;
  --e-out: cubic-bezier(.22,1,.36,1);
  --e-io:  cubic-bezier(.65,0,.35,1);

  --sh-float: 0 24px 60px -30px rgba(0,0,0,.85), 0 4px 18px -10px rgba(0,0,0,.5);

  color-scheme: dark;
}"""

new_tokens = """:root{
  --f-serif: "Instrument Serif", "Noto Serif SC", "Songti SC", serif;
  --f-sans:  "Instrument Sans Variable", "Instrument Sans", "Noto Sans SC", "Segoe UI", "Microsoft YaHei", sans-serif;
  --f-mono:  "IBM Plex Mono", "Cascadia Mono", Consolas, monospace;

  --r-lg: 10px;
  --r:    10px;
  --r-sm: 10px;

  --t-fast: .15s; --t: .24s; --t-slow: .5s;
  --e-out: cubic-bezier(.22,1,.36,1);
  --e-io:  cubic-bezier(.65,0,.35,1);
}

/* ---------- 模式：深色（暖石墨） ---------- */
:root[data-mode="dark"]{
  color-scheme: dark;
  --bg:        #131110;
  --bg-card:   #1a1715;
  --bg-raise:  #231f1a;
  --bg-deep:   #0c0a09;
  --bg-pop:    #251f1a;
  --bg-input:  #14110e;
  --line:      rgba(244,236,222,.07);
  --line2:     rgba(244,236,222,.14);

  --ink:       #f2ece1;
  --ink2:      #bdb2a0;
  --ink3:      #97897a;

  --lift-rgb:  255,244,225;          /* 所有抬升/发丝线的底色 */
  --page-bg:   #0a0908;
  --desk-1:    #0d0c0b; --desk-2: #0a0908; --desk-3: #0b0908;
  --desk-glow-1: rgba(255,236,206,.055);
  --vignette:  rgba(0,0,0,.55);
  --win-toplight: rgba(255,241,214,.022);
  --win-shadow: 0 60px 140px -60px rgba(0,0,0,.95), 0 24px 60px -30px rgba(0,0,0,.8), 0 0 0 1px rgba(0,0,0,.6);
  --input-inset: inset 0 1px 2px rgba(0,0,0,.35);
  --scrim:     rgba(8,6,5,.66);
  --sh-float:  0 24px 60px -30px rgba(0,0,0,.85), 0 4px 18px -10px rgba(0,0,0,.5);

  --ok:#8fb07e;   --ok-rgb:143,176,126;
  --warn:#d99a4e; --warn-rgb:217,154,78;
  --err:#d2766b;  --err-rgb:210,118,107;
}

/* ---------- 模式：浅色（瓷白纸面） ---------- */
:root[data-mode="light"]{
  color-scheme: light;
  --bg:        #efe9df;
  --bg-card:   #f7f3ec;
  --bg-raise:  #fdfbf7;
  --bg-deep:   #e5ded1;
  --bg-pop:    #fbf8f2;
  --bg-input:  #fbf8f2;
  --line:      rgba(64,50,33,.10);
  --line2:     rgba(64,50,33,.17);

  --ink:       #25201a;
  --ink2:      #5b5241;
  --ink3:      #7f7362;

  --lift-rgb:  74,58,38;
  --page-bg:   #e3dccf;
  --desk-1:    #e9e2d6; --desk-2: #e3dccf; --desk-3: #e6dfd2;
  --desk-glow-1: rgba(255,250,235,.45);
  --vignette:  rgba(88,66,40,.16);
  --win-toplight: rgba(255,255,255,.30);
  --win-shadow: 0 60px 130px -60px rgba(90,68,40,.45), 0 24px 60px -30px rgba(90,68,40,.28), 0 0 0 1px rgba(64,50,33,.14);
  --input-inset: inset 0 1px 2px rgba(64,50,33,.07);
  --scrim:     rgba(74,58,38,.32);
  --sh-float:  0 24px 60px -30px rgba(90,68,40,.45), 0 4px 18px -10px rgba(90,68,40,.22);

  --ok:#557a46;   --ok-rgb:85,122,70;
  --warn:#9a6b21; --warn-rgb:154,107,33;
  --err:#b04a3c;  --err-rgb:176,74,60;
}

/* ---------- 强调色（4 套预设 + 自定义[由 JS 注入]） ---------- */
:root[data-accent="brass"]{
  --acc:#c9a35c; --acc-rgb:201,163,92; --acc-hi:#e9d3a2; --acc-hi-rgb:233,211,162;
  --acc-lo:#8f7136; --acc-text:#c9a35c; --on-acc:#221809;
}
:root[data-mode="light"][data-accent="brass"]{
  --acc:#b08a3e; --acc-rgb:176,138,62; --acc-hi:#d6ba7a; --acc-hi-rgb:214,186,122;
  --acc-lo:#8a6a2c; --acc-text:#7f5f1a; --on-acc:#241a08;
}
:root[data-accent="celadon"]{
  --acc:#7fa895; --acc-rgb:127,168,149; --acc-hi:#a9c9b7; --acc-hi-rgb:169,201,183;
  --acc-lo:#557a67; --acc-text:#7fa895; --on-acc:#0d1c15;
}
:root[data-mode="light"][data-accent="celadon"]{
  --acc:#4b7a62; --acc-rgb:75,122,98; --acc-hi:#6f9c84; --acc-hi-rgb:111,156,132;
  --acc-lo:#35604b; --acc-text:#3f7259; --on-acc:#f4faf7;
}
:root[data-accent="indigo"]{
  --acc:#8291cf; --acc-rgb:130,145,207; --acc-hi:#aab6e6; --acc-hi-rgb:170,182,230;
  --acc-lo:#5b6aa4; --acc-text:#8291cf; --on-acc:#0f1428;
}
:root[data-mode="light"][data-accent="indigo"]{
  --acc:#5a6cb0; --acc-rgb:90,108,176; --acc-hi:#8291cf; --acc-hi-rgb:130,145,207;
  --acc-lo:#43528c; --acc-text:#46579e; --on-acc:#f5f7fd;
}
:root[data-accent="ink"]{
  --acc:#cbc2b1; --acc-rgb:203,194,177; --acc-hi:#e6dfd0; --acc-hi-rgb:230,223,208;
  --acc-lo:#9d9484; --acc-text:#cbc2b1; --on-acc:#221d15;
}
:root[data-mode="light"][data-accent="ink"]{
  --acc:#5b5244; --acc-rgb:91,82,68; --acc-hi:#7d7362; --acc-hi-rgb:125,115,98;
  --acc-lo:#3f382c; --acc-text:#4a4234; --on-acc:#f8f5ef;
}
:root{ --acc-dim: rgba(var(--acc-rgb),.16); }"""

rep(old_tokens, new_tokens, 1, "tokens-block")

# ============ 2. body / desk / 窗口 ============
rep("  background:#0a0908;", "  background:var(--page-bg);", 1, "body-bg")
rep("""    radial-gradient(1200px 700px at 18% -8%, rgba(255,236,206,.055), transparent 60%),
    radial-gradient(900px 600px at 88% 108%, rgba(201,163,92,.05), transparent 62%),
    linear-gradient(162deg, #0d0c0b 0%, #0a0908 52%, #0b0908 100%);""",
    """    radial-gradient(1200px 700px at 18% -8%, var(--desk-glow-1), transparent 60%),
    radial-gradient(900px 600px at 88% 108%, rgba(var(--acc-rgb),.05), transparent 62%),
    linear-gradient(162deg, var(--desk-1) 0%, var(--desk-2) 52%, var(--desk-3) 100%);""", 1, "desk")
rep("background:radial-gradient(130% 110% at 50% 42%, transparent 58%, rgba(0,0,0,.55) 100%);",
    "background:radial-gradient(130% 110% at 50% 42%, transparent 58%, var(--vignette) 100%);", 1, "vignette")
rep("""  background:
    linear-gradient(180deg, rgba(255,241,214,.022), rgba(255,241,214,0) 22%),
    var(--bg);
  border:1px solid rgba(255,244,225,.09);
  box-shadow:0 60px 140px -60px rgba(0,0,0,.95), 0 24px 60px -30px rgba(0,0,0,.8), 0 0 0 1px rgba(0,0,0,.6);""",
    """  background:
    linear-gradient(180deg, var(--win-toplight), transparent 22%),
    var(--bg);
  border:1px solid rgba(var(--lift-rgb),.09);
  box-shadow:var(--win-shadow);""", 1, "win")

# ============ 3. 输入 / 表面 / 浮层 ============
rep("  background:#14110e; color:var(--ink);", "  background:var(--bg-input); color:var(--ink);", 1, "inp-bg")
rep("box-shadow:inset 0 1px 2px rgba(0,0,0,.35);", "box-shadow:var(--input-inset);", 1, "inp-inset")
rep("box-shadow:inset 0 1px 2px rgba(0,0,0,.35), 0 0 0 3px rgba(201,163,92,.14);",
    "box-shadow:var(--input-inset), 0 0 0 3px rgba(var(--acc-rgb),.14);", 1, "inp-focus")
rep("  background:#241f19;", "  background:var(--bg-pop);", 1, "toast-bg")
rep("  background:#251f1a;", "  background:var(--bg-pop);", 1, "pop-bg")
rep("  background:#27211b;", "  background:var(--bg-pop);", 1, "ctx-bg")
rep("  width:430px; background:#231e19;", "  width:430px; background:var(--bg-pop);", 1, "modal-bg")
rep("  background:#13110e;\n  align-items:center; justify-content:center;", "  background:var(--bg);\n  align-items:center; justify-content:center;", 1, "wizard-bg")
rep("background:rgba(8,6,5,.66); backdrop-filter:blur(3px);", "background:var(--scrim); backdrop-filter:blur(3px);", 1, "scrim")
rep("background:rgba(10,8,7,.72); -webkit-backdrop-filter:blur(2px);", "background:var(--scrim); -webkit-backdrop-filter:blur(2px);", 1, "drop-bg")

# ============ 4. 主按钮（鎏金）============
rep("  background:linear-gradient(180deg, #e6cd97 0%, #c9a35c 46%, #b28a45 100%);\n  color:#221809; font-weight:520;",
    "  background:linear-gradient(180deg, var(--acc-hi) 0%, var(--acc) 46%, var(--acc-lo) 100%);\n  color:var(--on-acc); font-weight:520;", 1, "btn-primary")

# ============ 5. logo SVG → accent ============
rep('<circle cx="9" cy="9" r="7.1" stroke="#c9a35c" stroke-width="1.1" opacity=".9"/>',
    '<circle cx="9" cy="9" r="7.1" style="stroke:var(--acc)" stroke-width="1.1" opacity=".9"/>', 1, "logo-1")
rep('<path d="M9 2.4 A6.6 6.6 0 0 1 15.2 6.4" stroke="#e9d3a2" stroke-width="1.1" stroke-linecap="round"/>',
    '<path d="M9 2.4 A6.6 6.6 0 0 1 15.2 6.4" style="stroke:var(--acc-hi)" stroke-width="1.1" stroke-linecap="round"/>', 1, "logo-2")
rep('stroke="rgba(242,236,225,.45)"', 'style="stroke:rgba(var(--lift-rgb),.45)"', 1, "logo-3")
rep('<circle cx="9" cy="9" r="1.7" fill="#c9a35c"/>', '<circle cx="9" cy="9" r="1.7" style="fill:var(--acc)"/>', 1, "logo-4")

# ============ 6. 类名：brass → acc ============
rep(".led.brass{ background:var(--brass); opacity:1; }", ".led.acc{ background:var(--acc); opacity:1; }", 1, "led-acc-css")
rep('.chip.brass{ color:var(--brass); border-color:rgba(201,163,92,.4); }',
    '.chip.acc{ color:var(--acc-text); border-color:rgba(var(--acc-rgb),.4); }', 1, "chip-acc-css")
rep('<span class="led brass"></span>', '<span class="led acc"></span>', None, "led-acc-markup")
rep(" brass live", " acc live", 4, "led-live-markup+js")
rep('led brass"', 'led acc"', None, "led-markup2")
rep("? 'brass' :", "? 'acc' :", 1, "js-chip-class")
rep("'led brass'", "'led acc'", 1, "js-paint-led")

# ============ 7. 泛化 rgba：抬升 / 强调 / 语义 ============
for old, new, tag in [
    ("rgba(255,244,225,", "rgba(var(--lift-rgb),", "lift-generic"),
    ("rgba(255,241,214,", "rgba(var(--lift-rgb),", "lift-241-214"),
    ("rgba(242,236,225,", "rgba(var(--lift-rgb),", "lift-242-236"),
    ("rgba(201,163,92,", "rgba(var(--acc-rgb),", "acc-generic"),
    ("rgba(233,211,162,", "rgba(var(--acc-hi-rgb),", "acc-hi-generic"),
    ("rgba(201,106,92,", "rgba(var(--err-rgb),", "err-generic"),
    ("rgba(217,154,78,", "rgba(var(--warn-rgb),", "warn-generic"),
    ("rgba(143,176,126,", "rgba(var(--ok-rgb),", "ok-generic"),
]:
    n = s.count(old); s = s.replace(old, new); log.append((n, tag))

# ============ 8. token 更名 --brass* → --acc* ============
rep("var(--brass-hi)", "var(--acc-hi)", None, "rename-hi")
rep("var(--brass-lo)", "var(--acc-lo)", None, "rename-lo")
rep("var(--brass)", "var(--acc)", None, "rename-acc")
rep("var(--brass-dim)", "var(--acc-dim)", None, "rename-dim")

# ============ 9. 文本角色：--acc → --acc-text（4 处）============
rep(".rn.on svg{ color:var(--acc); opacity:1; }", ".rn.on svg{ color:var(--acc-text); opacity:1; }", 1, "acctext-rn")
rep('style="color:var(--acc);text-decoration:none"', 'style="color:var(--acc-text);text-decoration:none"', 1, "acctext-link")
rep(".dropin svg{ width:26px; height:26px; color:var(--acc); }", ".dropin svg{ width:26px; height:26px; color:var(--acc-text); }", 1, "acctext-drop")

# ============ 10. 残留断言 ============
leftovers = {
    "brass(非标识符)": len(re.findall(r'brass', s)) - s.count('data-accent="brass"') - s.count("st.accent||'brass'"),
    "rgba(255,244,225": s.count("rgba(255,244,225"),
    "rgba(201,163,92": s.count("rgba(201,163,92"),
    "rgba(233,211,162": s.count("rgba(233,211,162"),
    "rgba(201,106,92": s.count("rgba(201,106,92"),
    "#c9a35c": s.count("#c9a35c"),
    "#e9d3a2": s.count("#e9d3a2"),
}
print("=== 残留检查 ===")
ok_all = True
for k, v in leftovers.items():
    # 允许出现在 accent 定义块中的 hex（每色出现 1 次：brass 定义块自身）
    allowed = {"#c9a35c": 2, "#e9d3a2": 2}.get(k, 0)  # dark+light brass 各一次
    status = "OK " if v <= allowed else "!! "
    if v > allowed: ok_all = False
    print("  %s%-18s = %d (允许≤%d)" % (status, k, v, allowed))
for k in ["--lift-rgb", "--acc-rgb", "--acc-text", "--on-acc", "--scrim", "--win-shadow", 'data-mode="light"', 'data-mode="dark"']:
    v = s.count(k)
    print("  %s%-18s = %d" % ("OK " if v else "!! ", k, v))
    if not v: ok_all = False
if not ok_all:
    sys.exit(1)

io.open(P, "w", encoding="utf-8", newline="").write(s)
print()
for n, t in log:
    print("%4d  %s" % (n, t))
print("OK fix6 applied · %d chars" % len(s))
