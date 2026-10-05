# -*- coding: utf-8 -*-
"""生成 AYT-Launcher-v2.html：
- 从 v1 提取已验证区块（主题 token / 预置脚本 / 主题引擎 / 弹层与主题控件 CSS）
- 套上「门面」结构：单视图居中集群 + 接管式进度 + 极简标题栏
"""
import io, re

SRC = "AYT-Launcher-v1.html"
DST = "AYT-Launcher-v2.html"
s = io.open(SRC, encoding="utf-8").read()

# ---------- 提取 v1 区块 ----------
pre_start = s.index("<script>/* 主题预置")
pre_end = s.index("</script>", pre_start) + len("</script>")
PREPAINT = s[pre_start:pre_end]

tok_start = s.index(":root{", s.index("<style>"))
tok_end_marker = ":root{ --acc-dim: rgba(var(--acc-rgb),.16); }"
tok_end = s.index(tok_end_marker) + len(tok_end_marker)
TOKENS = s[tok_start:tok_end]

pop_start = s.index(".pop{")
pop_end_marker = ".pop-sep{ height:1px; background:var(--line); margin:6px 8px; }"
pop_end = s.index(pop_end_marker, pop_start) + len(pop_end_marker)
POPS = s[pop_start:pop_end]

th_start = s.rindex("/* ===", 0, s.index("§T 外观 / 主题控件"))
th_end_marker = "@media (prefers-reduced-motion: reduce){ html.theming, html.theming *{ transition:none !important; } }"
th_end = s.index(th_end_marker, th_start) + len(th_end_marker)
THEMECSS = s[th_start:th_end]

toast_start = s.index(".toasts{")
toast_end_marker = ".toast .x{ flex-shrink:0; }"
toast_end = s.index(toast_end_marker, toast_start) + len(toast_end_marker)
TOASTS = s[toast_start:toast_end]

tjs_start = s.index("/* ---------- 主题系统 ---------- */")
tjs_end_marker = "applyTheme(false);"
tjs_end = s.index(tjs_end_marker, tjs_start) + len(tjs_end_marker)
THEMEJS = s[tjs_start:tjs_end]

for name, blk in [("PREPAINT", PREPAINT), ("TOKENS", TOKENS), ("POPS", POPS), ("THEMECSS", THEMECSS), ("TOASTS", TOASTS), ("THEMEJS", THEMEJS)]:
    print("%-9s %5d chars" % (name, len(blk)))

# ---------- v2 模板 ----------
T = """<!doctype html>
<html lang="zh-CN" data-mode="dark" data-accent="brass">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<meta name="color-scheme" content="dark light" />
<title>Auto YOLO Training · 启动器 v2</title>
@@PREPAINT@@

<!-- 字体：本地化（fonts/，离线可用） -->
<link rel="stylesheet" href="fonts/instrument-serif-400.css" />
<link rel="stylesheet" href="fonts/noto-serif-sc-400.css" />
<link rel="stylesheet" href="fonts/instrument-sans-var.css" />
<link rel="stylesheet" href="fonts/noto-sans-sc-400.css" />
<link rel="stylesheet" href="fonts/noto-sans-sc-500.css" />
<link rel="stylesheet" href="fonts/ibm-plex-mono-400.css" />
<link rel="stylesheet" href="fonts/ibm-plex-mono-500.css" />

<style>
/* ==========================================================================
   AYT 启动器 v2 ——「门面」
   参考机制：Comfy Desktop 1.0.38（居中集群 / 单动作 / 接管式进度 / 渐进披露）
   保留身份：暖石墨 · 鎏金铜 · 瓷白 + 主题系统（深/浅 × 四强调色 + 自定义）
   ========================================================================== */

@@TOKENS@@

*{ box-sizing:border-box; margin:0; padding:0; }
[hidden]{ display:none !important; }
html,body{ height:100%; }
body{
  background:var(--page-bg); color:var(--ink);
  font-family:var(--f-sans); font-size:13px; line-height:1.5; font-weight:440;
  -webkit-font-smoothing:antialiased; line-break:strict; font-synthesis:none;
  overflow:hidden;
}
::selection{ background:rgba(var(--acc-rgb),.28); }

/* ---------- 桌面 + 舞台 ---------- */
.desk{
  position:fixed; inset:0;
  background:
    radial-gradient(1200px 700px at 18% -8%, var(--desk-glow-1), transparent 60%),
    linear-gradient(162deg, var(--desk-1) 0%, var(--desk-2) 52%, var(--desk-3) 100%);
}
.desk::after{ content:''; position:absolute; inset:0;
  background:radial-gradient(130% 110% at 50% 42%, transparent 58%, var(--vignette) 100%); }
.stage{ position:fixed; inset:0; display:flex; align-items:center; justify-content:center; }
.stage-inner{ transform-origin:center center; }

/* ---------- 窗口 ---------- */
.win{
  width:1400px; height:880px; border-radius:10px;
  background:linear-gradient(180deg, var(--win-toplight), transparent 22%), var(--bg);
  border:1px solid rgba(var(--lift-rgb),.09);
  box-shadow:var(--win-shadow);
  overflow:hidden; position:relative; display:flex; flex-direction:column;
  animation:win-in .24s var(--e-out) both;
}
@keyframes win-in{ from{ opacity:0; transform:scale(.985) } to{ opacity:1; transform:none } }

/* ---------- 标题栏（极简：品牌 + 三个图标钮 + 窗口钮） ---------- */
.tbar{ height:44px; flex-shrink:0; display:flex; align-items:center; gap:12px;
  padding-left:18px; border-bottom:1px solid var(--line); background:rgba(var(--lift-rgb),.012); }
.tb-brand{ display:flex; align-items:center; gap:10px; min-width:0; }
.tb-mark{ width:17px; height:17px; flex-shrink:0; }
.tb-name{ font-family:var(--f-serif); font-size:16px; letter-spacing:.01em; color:var(--ink); white-space:nowrap; }
.tb-c{ flex:1; }
.tb-r{ display:flex; align-items:center; }
.tbi{ width:34px; height:30px; margin-right:2px; border:0; border-radius:8px; background:transparent;
  display:grid; place-items:center; color:var(--ink3); cursor:pointer;
  transition:background var(--t-fast) var(--e-io), color var(--t-fast) var(--e-io); }
.tbi:hover{ color:var(--ink); background:rgba(var(--lift-rgb),.06); }
.tbi svg{ width:14px; height:14px; }
.wctl{ display:flex; margin-left:6px; }
.wctl button{ width:46px; height:44px; border:0; background:transparent; cursor:pointer;
  display:grid; place-items:center; color:var(--ink3);
  transition:background var(--t-fast) var(--e-io), color var(--t-fast) var(--e-io); }
.wctl button:hover{ background:rgba(var(--lift-rgb),.06); color:var(--ink); }
.wctl button.close:hover{ background:#b8332a; color:#fff; }
.wctl svg{ width:11px; height:11px; }

/* ---------- 主区：居中集群 ---------- */
.hero{ flex:1; min-height:0; display:flex; flex-direction:column; align-items:center; justify-content:center;
  gap:14px; padding:24px 40px 40px; text-align:center; }
.hero-logo{ width:46px; height:46px; color:var(--acc); margin-bottom:6px; }
.wordmark{ font-family:var(--f-serif); font-weight:400; font-size:34px; line-height:1.1; letter-spacing:.005em; }

.btn-primary{
  margin-top:20px; height:48px; padding:0 32px; border:0; border-radius:10px;
  display:inline-flex; align-items:center; gap:10px;
  background:linear-gradient(180deg, var(--acc-hi) 0%, var(--acc) 46%, var(--acc-lo) 100%);
  color:var(--on-acc); font-family:var(--f-sans); font-size:14px; font-weight:520; letter-spacing:.01em;
  cursor:pointer;
  box-shadow:inset 0 1px 0 rgba(255,240,205,.7), 0 12px 30px -16px rgba(var(--acc-rgb),.6);
  transition:filter var(--t-fast) var(--e-io), transform var(--t-fast) var(--e-io);
}
.btn-primary:hover{ filter:brightness(1.06); }
.btn-primary:active{ transform:translateY(1px) scale(.995); }
.btn-primary svg{ width:14px; height:14px; }
.btn-primary:disabled{ opacity:.55; cursor:default; }

.qrow{ display:flex; align-items:center; gap:4px; margin-top:4px; }
.qbtn{ height:30px; padding:0 12px; border:0; border-radius:8px; background:transparent;
  color:var(--ink2); font-family:var(--f-sans); font-size:13px; cursor:pointer;
  transition:color var(--t-fast) var(--e-io), background var(--t-fast) var(--e-io); }
.qbtn:hover{ color:var(--ink); background:rgba(var(--lift-rgb),.05); }
.qbtn[hidden]{ display:none; }
.qbtn.danger{ color:var(--err); }
.qbtn.danger:hover{ background:rgba(var(--err-rgb),.09); color:var(--err); }

.status{ display:inline-flex; align-items:center; gap:8px; margin-top:16px;
  font-size:12px; color:var(--ink3); min-height:16px; }
.status .led{ width:6px; height:6px; }

.led{ width:6px; height:6px; border-radius:999px; flex-shrink:0; background:rgba(var(--lift-rgb),.22); }
.led.ok{ background:var(--ok); }
.led.warn{ background:var(--warn); }
.led.err{ background:var(--err); }
.led.acc{ background:var(--acc); opacity:1; }
.led.live{ background:var(--acc); box-shadow:0 0 8px -1px rgba(var(--acc-rgb),.85); animation:breath 2.8s var(--e-io) infinite; }
.led.live.ok{ background:var(--ok); animation:none; box-shadow:none; }
@keyframes breath{ 0%,100%{ opacity:1 } 50%{ opacity:.4 } }

.tstrip{ display:none; flex-direction:column; align-items:center; gap:9px; margin-top:14px; }
.tstrip.on{ display:flex; animation:scr-in .3s var(--e-out) both; }
.tstrip .line{ font-size:12px; color:var(--ink2); font-variant-numeric:tabular-nums; }
.tstrip .line .mono{ font-family:var(--f-mono); color:var(--ink); }
.tstrip .bar{ width:320px; height:3px; border-radius:999px; background:rgba(var(--lift-rgb),.08); overflow:hidden; }
.tstrip .bar i{ display:block; height:100%; width:74%; background:var(--acc);
  box-shadow:0 0 10px -2px rgba(var(--acc-rgb),.8); }

/* ---------- 底栏 ---------- */
.fbar{ height:34px; flex-shrink:0; display:flex; align-items:center; gap:12px;
  padding:0 18px; border-top:1px solid var(--line); font-size:12px; color:var(--ink3); }
.fbar .mono{ font-family:var(--f-mono); font-size:12px; }
.fbar .sp{ flex:1; }

/* ---------- 接管层（启动/错误/首启）—— 不遮标题栏，演示时可随时切换 ---------- */
.takeover{ position:absolute; top:44px; left:0; right:0; bottom:0; z-index:60; display:none; background:var(--bg); }
.takeover.on{ display:block; animation:tk-in .26s var(--e-out) both; }
@keyframes tk-in{ from{ opacity:0; transform:translateY(8px) } to{ opacity:1; transform:none } }
.tk-logo{ position:absolute; top:16px; left:16px; width:20px; height:20px; color:var(--acc); }
.tk-body{ position:absolute; inset:0; display:flex; flex-direction:column; align-items:center;
  justify-content:center; gap:14px; padding:24px 40px 36px; text-align:center; }
.tk-banner{ display:inline-flex; align-items:center; gap:10px; font-size:16px; color:var(--ink); min-height:24px; }
.tk-banner svg{ width:17px; height:17px; }
.tk-banner.err{ color:var(--err); }
.tk-msg{ font-size:13px; color:var(--ink2); line-height:1.7; max-width:46ch; }
.tk-steps{ display:flex; flex-direction:column; gap:11px; min-width:320px; margin-top:8px; }
.tk-step{ display:flex; align-items:center; gap:11px; height:22px; font-size:13px; color:var(--ink3);
  opacity:0; transform:translateY(4px); }
.tk-step.in{ animation:scr-in .3s var(--e-out) both; }
@keyframes scr-in{ from{ opacity:0; transform:translateY(4px) } to{ opacity:1; transform:none } }
.tk-step .nm{ color:inherit; }
.tk-step.done .nm{ color:var(--ink2); }
.tk-step .sp{ flex:1; }
.tk-step .v{ font-family:var(--f-mono); font-size:12px; color:var(--ink3); font-variant-numeric:tabular-nums; }
.tk-actions{ display:flex; align-items:center; gap:10px; margin-top:16px; min-height:36px; }

.btn{ height:36px; padding:0 16px; border-radius:8px; border:1px solid var(--line2); background:transparent;
  color:var(--ink); font-family:var(--f-sans); font-size:13px; cursor:pointer;
  display:inline-flex; align-items:center; gap:8px;
  transition:background var(--t-fast) var(--e-io), border-color var(--t-fast) var(--e-io), color var(--t-fast) var(--e-io); }
.btn:hover{ background:rgba(var(--lift-rgb),.05); }
.btn svg{ width:13px; height:13px; }
.btn.primary{ border:0; background:var(--acc); color:var(--on-acc); font-weight:520; }
.btn.primary:hover{ filter:brightness(1.06); background:var(--acc); }
.btn.danger{ color:var(--err); border-color:rgba(var(--err-rgb),.5); }
.btn.danger:hover{ background:rgba(var(--err-rgb),.1); }
.btn:disabled{ opacity:.55; cursor:default; }

/* ---------- 弹层（外观/设置/场景） ---------- */
@@POPS@@

@@THEMECSS@@

/* 设置弹层行 */
.sline{ display:flex; align-items:center; gap:10px; padding:7px 10px; min-height:34px; }
.sline .lbl{ flex:1; min-width:0; font-size:12px; color:var(--ink2); }
.sline .inp-mini{ width:88px; height:28px; padding:0 9px; border:1px solid var(--line2); border-radius:8px;
  background:var(--bg-input); color:var(--ink); font-family:var(--f-mono); font-size:12px; outline:none;
  font-variant-numeric:tabular-nums; }
.sline .inp-mini:focus{ border-color:var(--acc); }
.switch{ position:relative; width:36px; height:20px; flex-shrink:0; border-radius:999px;
  border:1px solid var(--line2); background:var(--bg-deep); cursor:pointer; padding:0;
  transition:background var(--t) var(--e-io), border-color var(--t) var(--e-io); }
.switch::after{ content:''; position:absolute; top:2px; left:2px; width:14px; height:14px; border-radius:999px;
  background:var(--ink2); transition:transform var(--t) var(--e-out), background var(--t) var(--e-io); }
.switch.on{ background:rgba(var(--acc-rgb),.26); border-color:rgba(var(--acc-rgb),.55); }
.switch.on::after{ transform:translateX(16px); background:var(--acc-hi); }
.sp-foot{ display:flex; align-items:center; gap:6px; margin:6px 10px 2px; padding-top:9px;
  border-top:1px solid var(--line); font-size:12px; color:var(--ink3); }
.sp-foot a{ color:var(--acc-text); text-decoration:none; cursor:pointer; }
.sp-foot a:hover{ text-decoration:underline; }

@@TOASTS@@

/* ---------- 主题切换过渡（仅切换瞬间） ---------- */
html.theming, html.theming *, html.theming *::before, html.theming *::after{
  transition:background-color .22s ease, border-color .22s ease, color .22s ease, box-shadow .22s ease !important;
}
@media (prefers-reduced-motion: reduce){ html.theming, html.theming *{ transition:none !important; } }
html.theming *{ animation-play-state:running; }

:focus-visible{ outline:2px solid rgba(var(--acc-rgb),.8); outline-offset:2px; }
</style>
</head>
<body>
<div class="desk"></div>
<div class="stage"><div class="stage-inner" id="stageInner">
  <div class="win" id="win">

    <!-- 标题栏 -->
    <header class="tbar">
      <div class="tb-brand">
        <svg class="tb-mark" viewBox="0 0 18 18" fill="none" aria-hidden="true">
          <circle cx="9" cy="9" r="7.1" style="stroke:var(--acc)" stroke-width="1.1" opacity=".9"/>
          <path d="M9 2.4 A6.6 6.6 0 0 1 15.2 6.4" style="stroke:var(--acc-hi)" stroke-width="1.1" stroke-linecap="round"/>
          <path d="M3.4 5.6 A6.6 6.6 0 0 0 9 15.6" style="stroke:rgba(var(--lift-rgb),.45)" stroke-width="1.1" stroke-linecap="round"/>
          <circle cx="9" cy="9" r="1.7" style="fill:var(--acc)"/>
        </svg>
        <span class="tb-name">Auto YOLO Training</span>
      </div>
      <div class="tb-c"></div>
      <div class="tb-r">
        <button class="tbi" id="themeBtn" type="button" title="外观" aria-label="外观" aria-haspopup="true">
          <svg viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="5.2" stroke="currentColor" stroke-width="1.1"/><path d="M7 1.8a5.2 5.2 0 0 1 0 10.4Z" fill="currentColor" opacity=".5"/></svg>
        </button>
        <button class="tbi" id="setBtn" type="button" title="设置" aria-label="设置" aria-haspopup="true">
          <svg viewBox="0 0 14 14" fill="none"><path d="M2 4h10M2 7h10M2 10h10" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/><circle cx="5" cy="4" r="1.5" fill="var(--bg)" stroke="currentColor" stroke-width="1.1"/><circle cx="9.5" cy="7" r="1.5" fill="var(--bg)" stroke="currentColor" stroke-width="1.1"/><circle cx="4.5" cy="10" r="1.5" fill="var(--bg)" stroke="currentColor" stroke-width="1.1"/></svg>
        </button>
        <button class="tbi" id="scenarioBtn" type="button" title="场景演示" aria-label="场景演示" aria-haspopup="true">
          <svg viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.1"/><circle cx="7" cy="7" r="1.4" fill="currentColor"/></svg>
        </button>
        <div class="wctl">
          <button type="button" aria-label="最小化" title="最小化"><svg viewBox="0 0 11 11" fill="none"><path d="M1 5.5h9" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/></svg></button>
          <button type="button" aria-label="最大化" title="最大化"><svg viewBox="0 0 11 11" fill="none"><rect x="1.2" y="1.2" width="8.6" height="8.6" rx="1.4" stroke="currentColor" stroke-width="1.1"/></svg></button>
          <button type="button" class="close" aria-label="关闭" title="关闭"><svg viewBox="0 0 11 11" fill="none"><path d="M1.6 1.6l7.8 7.8M9.4 1.6L1.6 9.4" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/></svg></button>
        </div>
      </div>
    </header>

    <!-- 主区：居中集群 -->
    <main class="hero">
      <svg class="hero-logo" viewBox="0 0 18 18" fill="none" aria-hidden="true">
        <circle cx="9" cy="9" r="7.1" style="stroke:var(--acc)" stroke-width="1.05" opacity=".9"/>
        <path d="M9 2.4 A6.6 6.6 0 0 1 15.2 6.4" style="stroke:var(--acc-hi)" stroke-width="1.05" stroke-linecap="round"/>
        <path d="M3.4 5.6 A6.6 6.6 0 0 0 9 15.6" style="stroke:rgba(var(--lift-rgb),.45)" stroke-width="1.05" stroke-linecap="round"/>
        <circle cx="9" cy="9" r="1.7" style="fill:var(--acc)"/>
      </svg>
      <h1 class="wordmark">Auto YOLO Training</h1>
      <button class="btn-primary" id="btnPrimary" type="button">
        <svg id="primaryIcon" viewBox="0 0 14 14" fill="none"><path d="M4.2 2.6 11.4 7l-7.2 4.4V2.6Z" stroke="currentColor" stroke-width="1.25" stroke-linejoin="round"/></svg>
        <span id="primaryLabel">启动控制台</span>
      </button>
      <div class="qrow">
        <button class="qbtn" id="btnServe" type="button">推理服务</button>
        <button class="qbtn" id="btnStop" type="button" hidden>停止控制台</button>
        <button class="qbtn" id="btnImport" type="button" hidden>导入数据集</button>
        <button class="qbtn" id="btnSettings2" type="button">设置</button>
      </div>
      <div class="status"><span class="led ok" id="statusLed"></span><span id="statusText">环境就绪 · RTX 5080 Laptop</span></div>
      <div class="tstrip" id="tstrip">
        <div class="line"><span class="mono">data_auto</span> · 37/50 轮 · mAP@50 <span class="mono">0.611</span></div>
        <div class="bar"><i></i></div>
      </div>
    </main>

    <div class="fbar">
      <span class="mono">v0.1.0 · 9e05411</span>
      <span class="sp"></span>
      <span class="mono" id="fbRight">控制台 — · 推理 —</span>
    </div>

    <!-- 接管层 -->
    <div class="takeover" id="takeover" aria-live="polite">
      <svg class="tk-logo" viewBox="0 0 18 18" fill="none" aria-hidden="true">
        <circle cx="9" cy="9" r="7.1" style="stroke:var(--acc)" stroke-width="1.1" opacity=".9"/>
        <circle cx="9" cy="9" r="1.7" style="fill:var(--acc)"/>
      </svg>
      <div class="tk-body">
        <div class="tk-banner" id="tkBanner" hidden><svg id="tkIcon" viewBox="0 0 14 14" fill="none"></svg><span id="tkTitle"></span></div>
        <div class="tk-msg" id="tkMsg" hidden></div>
        <div class="tk-steps" id="tkSteps"></div>
        <div class="tk-actions" id="tkActions"></div>
      </div>
    </div>

    <!-- 弹层 -->
    <div class="pop" id="themePop">
      <div class="ph"><div class="a">外观</div><div class="b">保存在本地 · 只影响启动器</div></div>
      <div class="trow">
        <span class="trow-l">模式</span>
        <div class="tseg" id="tpMode">
          <button type="button" data-mode="dark">深色</button>
          <button type="button" data-mode="light">浅色</button>
          <button type="button" data-mode="system">系统</button>
        </div>
      </div>
      <div class="trow">
        <span class="trow-l">强调色</span>
        <div class="tsw" id="tpAcc">
          <button type="button" class="sw-brass" data-accent="brass" title="鎏金" aria-label="强调色：鎏金"></button>
          <button type="button" class="sw-celadon" data-accent="celadon" title="青瓷" aria-label="强调色：青瓷"></button>
          <button type="button" class="sw-indigo" data-accent="indigo" title="靛蓝" aria-label="强调色：靛蓝"></button>
          <button type="button" class="sw-ink" data-accent="ink" title="砚墨" aria-label="强调色：砚墨"></button>
          <button type="button" class="tcustom" data-accent="custom" title="自定义…" aria-label="自定义强调色"><input type="color" id="tpColor" value="#c9a35c" tabindex="-1" aria-hidden="true" /></button>
        </div>
      </div>
    </div>

    <div class="pop" id="setPop">
      <div class="ph"><div class="a">设置</div><div class="b">更多设置在控制台里</div></div>
      <div class="sline"><span class="lbl">控制台端口</span><input class="inp-mini" value="8080" inputmode="numeric" /></div>
      <div class="sline"><span class="lbl">推理服务端口</span><input class="inp-mini" value="8000" inputmode="numeric" /></div>
      <div class="sline"><span class="lbl">自动打开浏览器</span><button class="switch on" type="button" role="switch" aria-checked="true"></button></div>
      <div class="sline"><span class="lbl">关闭窗口时最小化到托盘</span><button class="switch on" type="button" role="switch" aria-checked="true"></button></div>
      <div class="sp-foot"><span>训练默认、通知、路径</span><span class="sp" style="flex:1"></span><a id="spMore">在控制台打开 →</a></div>
    </div>

    <div class="pop" id="scenarioPop">
      <div class="ph"><div class="a">场景演示</div><div class="b">仅影响原型 · 不执行真实命令</div></div>
      <button class="pop-i on" type="button" data-scene="idle"><span class="led ok"></span>就绪<span class="sp"></span></button>
      <button class="pop-i" type="button" data-scene="launching"><span class="led acc"></span>启动中<span class="sp"></span></button>
      <button class="pop-i" type="button" data-scene="running"><span class="led ok"></span>运行中<span class="sp"></span></button>
      <button class="pop-i" type="button" data-scene="training"><span class="led acc"></span>训练中<span class="sp"></span></button>
      <button class="pop-i" type="button" data-scene="portbusy"><span class="led err"></span>端口被占用<span class="sp"></span></button>
      <button class="pop-i" type="button" data-scene="firstrun"><span class="led"></span>首次启动<span class="sp"></span></button>
      <button class="pop-i" type="button" data-scene="empty"><span class="led warn"></span>空环境<span class="sp"></span></button>
      <div class="pop-sep"></div>
      <button class="pop-i" type="button" id="popClose"><span class="sp"></span>关闭<span class="hint">Esc</span></button>
    </div>

    <div class="toasts" id="toasts"></div>
  </div>
</div></div>

<script>
'use strict';
/* ==========================================================================
   AYT 启动器 v2 · 原型交互（所有网络类行为均为演示）
   ========================================================================== */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const RM = matchMedia('(prefers-reduced-motion: reduce)').matches;
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

@@THEMEJS@@

/* ---------- 状态与文案 ---------- */
const state = { scene:'idle', console:'stopped', serve:'stopped' };
let seqToken = 0;

const PRIMARY_ICON = {
  play:  '<path d="M4.2 2.6 11.4 7l-7.2 4.4V2.6Z" stroke="currentColor" stroke-width="1.25" stroke-linejoin="round"/>',
  open:  '<path d="M5.5 3H3.5A1.5 1.5 0 0 0 2 4.5v6A1.5 1.5 0 0 0 3.5 12h6A1.5 1.5 0 0 0 11 10.5V8.5M8 2h4v4M11.5 2.5 6 8" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round"/>'
};

function icon(name){ if (name === 'play') return '<path d="M4.2 2.6 11.4 7l-7.2 4.4V2.6Z" stroke="currentColor" stroke-width="1.25" stroke-linejoin="round"/>';
  return PRIMARY_ICON.open; }

/* ---------- 接管层公共 ---------- */
let tkTimers = [];
function tkClear(){ tkTimers.forEach(t => clearTimeout(t)); tkTimers = []; }
function tkOpen(){ $('#takeover').classList.add('on'); }
function tkClose(){ tkClear(); $('#takeover').classList.remove('on'); }
function tkBanner(txt, tone){
  const b = $('#tkBanner');
  if (!txt){ b.hidden = true; return; }
  b.hidden = false; b.classList.toggle('err', tone === 'err');
  $('#tkTitle').textContent = txt;
  $('#tkIcon').innerHTML = tone === 'err'
    ? '<path d="M3.5 3.5l7 7M10.5 3.5l-7 7" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>'
    : '<circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.3"/><path d="M7 4.6v3.4l2.2 1.3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>';
}
function tkMsg(txt){ const m = $('#tkMsg'); m.hidden = !txt; if (txt) m.textContent = txt; }
function tkSteps(items){ $('#tkSteps').innerHTML = ''; return items.map(([nm, v]) => {
  const d = document.createElement('div'); d.className = 'tk-step';
  d.innerHTML = '<span class="led"></span><span class="nm"></span><span class="sp"></span><span class="v"></span>';
  d.querySelector('.nm').textContent = nm; d.querySelector('.v').textContent = v || '';
  $('#tkSteps').appendChild(d); return d; }); }
function tkActions(items){
  const host = $('#tkActions'); host.innerHTML = '';
  items.forEach(([label, cls, fn]) => {
    const b = document.createElement('button'); b.type = 'button'; b.className = 'btn' + (cls ? ' ' + cls : '');
    b.textContent = label; b.onclick = fn; host.appendChild(b);
  });
}

/* ---------- 集群绘制 ---------- */
function paintUI(){
  const scene = state.scene;
  const pLabel = $('#primaryLabel'), pIcon = $('#primaryIcon'), btnStop = $('#btnStop'), btnServe = $('#btnServe'), btnImport = $('#btnImport');
  const led = $('#statusLed'), stx = $('#statusText'), strip = $('#tstrip'), fb = $('#fbRight');

  btnStop.hidden = btnImport.hidden = true;
  strip.classList.remove('on');
  pIcon.innerHTML = icon('play');
  pLabel.textContent = '启动控制台';

  if (scene === 'running'){
    pLabel.textContent = '打开控制台'; pIcon.innerHTML = icon('open');
    btnStop.hidden = false; btnStop.textContent = '停止控制台';
  } else if (scene === 'training'){
    pLabel.textContent = '打开监控'; pIcon.innerHTML = icon('open');
    btnStop.hidden = false; btnStop.textContent = '停止训练';
  } else if (scene === 'empty'){
    btnImport.hidden = false;
  }

  if (scene === 'training'){ led.className = 'led acc live'; stx.textContent = '训练中 · data_auto'; strip.classList.add('on'); }
  else if (scene === 'running'){ led.className = 'led ok'; stx.textContent = '控制台运行中 · 127.0.0.1:8080'; }
  else if (scene === 'empty'){ led.className = 'led warn'; stx.textContent = '还没有数据集'; }
  else if (scene === 'portbusy'){ led.className = 'led err'; stx.textContent = '端口 8080 被占用'; }
  else if (scene === 'firstrun'){ led.className = 'led'; stx.textContent = '等待首次设置'; }
  else { led.className = 'led ok'; stx.textContent = '环境就绪 · RTX 5080 Laptop'; }

  btnServe.textContent = state.serve === 'running' ? '停止推理' : '推理服务';
  btnServe.classList.toggle('danger', state.serve === 'running');
  fb.textContent = '控制台 ' + (state.console === 'running' ? ':8080' : '—') + ' · 推理 ' + (state.serve === 'running' ? ':8000' : '—');

  $$('#scenarioPop .pop-i[data-scene]').forEach(el => el.classList.toggle('on', el.dataset.scene === scene));
}

/* ---------- 场景切换 ---------- */
function setScene(name){
  seqToken++;
  state.scene = name;
  tkClear();
  if (name === 'running' || name === 'training') state.console = 'running';
  else if (name !== 'launching') state.console = 'stopped';
  if (name === 'launching'){ launchConsole(false); return; }
  if (name === 'portbusy'){ showPortbusy(); }
  else if (name === 'firstrun'){ showFirstrun(); }
  else tkClose();
  paintUI();
}

/* ---------- 启动序列（接管层） ---------- */
async function launchConsole(interactive){
  const token = ++seqToken;
  state.scene = 'launching'; state.console = 'starting';
  paintUI();
  tkOpen(); tkBanner('正在启动控制台', 'run'); tkMsg('');
  const steps = tkSteps([
    ['准备环境', 'py3.12.7 · torch 2.9.0'],
    ['校验构建产物', 'web/dist'],
    ['绑定端口', '127.0.0.1:8080'],
    ['就绪', '']
  ]);
  async function cancelFn(){ if (token !== seqToken) return; tkClear(); state.scene = 'idle'; state.console = 'stopped'; tkClose(); paintUI(); }
  tkActions([['取消', '', cancelFn]]);
  for (let i = 0; i < steps.length; i++){
    if (token !== seqToken) return;
    await sleep(RM ? 60 : 520);
    if (token !== seqToken) return;
    steps[i].classList.add('in'); steps[i].querySelector('.led').className = 'led acc';
    await sleep(RM ? 40 : 260);
    if (token !== seqToken) return;
    steps[i].classList.add('done'); steps[i].querySelector('.led').className = 'led ok';
  }
  await sleep(RM ? 80 : 300);
  if (token !== seqToken) return;
  tkClose(); state.scene = 'running'; state.console = 'running'; paintUI();
  toast('ok', '控制台已启动', '127.0.0.1:8080 已在浏览器打开');
}

async function launchServe(){
  const token = ++seqToken;
  const prev = state.scene;
  tkOpen(); tkBanner('正在启动推理服务', 'run'); tkMsg('');
  const steps = tkSteps([
    ['校验模型', 'best_20260918_002350.pt'],
    ['加载到显存', '5.4 GB'],
    ['就绪', '127.0.0.1:8000']
  ]);
  tkActions([['取消', '', () => { if (token !== seqToken) return; tkClear(); tkClose(); paintUI(); }]]);
  for (let i = 0; i < steps.length; i++){
    if (token !== seqToken) return;
    await sleep(RM ? 60 : 520);
    steps[i].classList.add('in'); steps[i].querySelector('.led').className = 'led acc';
    await sleep(RM ? 40 : 240);
    steps[i].classList.add('done'); steps[i].querySelector('.led').className = 'led ok';
  }
  await sleep(RM ? 80 : 280);
  if (token !== seqToken) return;
  state.serve = 'running'; state.scene = prev; tkClose(); paintUI();
  toast('ok', '推理服务已启动', '127.0.0.1:8000');
}

/* ---------- 错误 / 首启接管 ---------- */
function showPortbusy(){
  tkOpen(); tkBanner('端口 8080 被占用', 'err');
  tkMsg('可能是上一次未退出的控制台（PID 12345）。');
  tkSteps([]);
  tkActions([
    ['改用 8081 启动', 'primary', () => { tkClose(); state.scene = 'idle'; state.console = 'stopped'; paintUI(); toast('ok', '已改用 8081', '控制台将在 127.0.0.1:8081 启动'); }],
    ['结束占用进程', 'danger', () => { tkClose(); state.scene = 'idle'; state.console = 'stopped'; paintUI(); toast('warn', '已结束 PID 12345', '再次启动即可使用 8080'); }]
  ]);
}
function showFirstrun(){
  tkOpen(); tkBanner('首次启动 · 环境检测', 'run'); tkMsg('');
  const steps = tkSteps([
    ['Python 3.12.7', '通过'],
    ['CUDA 可用 · RTX 5080 Laptop', '通过'],
    ['磁盘可用 321 GB', '通过'],
    ['数据集 6 · 权重 27', '通过'],
    ['Webhook 通知未配置', '可稍后']
  ]);
  tkActions([['开始使用', 'primary', () => { tkClose(); state.scene = 'idle'; paintUI(); }]]);
  steps.forEach((el, i) => {
    tkTimers.push(setTimeout(() => {
      el.classList.add('in');
      el.querySelector('.led').className = 'led ' + (i === steps.length - 1 ? 'warn' : 'ok');
    }, RM ? 40 : 240 + i * 360));
  });
}

/* ---------- 交互 ---------- */
$('#btnPrimary').onclick = () => {
  if (state.scene === 'running' || state.console === 'running') toast('ok', '已在浏览器打开', '127.0.0.1:8080');
  else if (state.scene === 'training') toast('ok', '打开监控', '正在打开控制台监控页（原型演示）');
  else launchConsole(true);
};
$('#btnServe').onclick = () => {
  if (state.serve === 'running'){ state.serve = 'stopped'; paintUI(); toast('warn', '推理服务已停止', '127.0.0.1:8000'); }
  else launchServe();
};
$('#btnStop').onclick = () => {
  const wasTraining = state.scene === 'training';
  state.console = 'stopped'; state.scene = 'idle'; paintUI();
  toast('warn', wasTraining ? '训练已停止' : '控制台已停止', wasTraining ? '检查点已保留：weights/last.pt' : '');
};
$('#btnImport').onclick = () => { state.scene = 'idle'; paintUI(); toast('ok', '导入数据集（原型演示）', '真实版本将上传、解压、扫描并校验'); };
$('#btnSettings2').onclick = (e) => { e.stopPropagation(); openPop('#setPop'); };
$('#setBtn').onclick = (e) => { e.stopPropagation(); openPop('#setPop'); };
$('#spMore').onclick = () => { toast('ok', '更多设置在控制台', '训练默认 · 通知 · 路径（原型演示）'); };
/* 三钮互斥（themeBtn 的开合在主题引擎内，这里补设置/场景，并绑定场景弹层） */
$('#themeBtn').addEventListener('click', () => $('#setPop').classList.remove('on'));
$('#scenarioBtn').onclick = (e) => { e.stopPropagation(); $('#themePop').classList.remove('on'); $('#setPop').classList.remove('on'); $('#scenarioPop').classList.toggle('on'); };

function openPop(sel){
  ['#themePop', '#setPop', '#scenarioPop'].forEach(p => { if (p !== sel) $(p).classList.remove('on'); });
  $(sel).classList.toggle('on');
}
addEventListener('click', (e) => {
  if (!e.target.closest('#setPop') && !e.target.closest('#setBtn') && !e.target.closest('#btnSettings2')) $('#setPop').classList.remove('on');
});
$$('#scenarioPop .pop-i[data-scene]').forEach(el => el.onclick = () => { setScene(el.dataset.scene); $('#scenarioPop').classList.remove('on'); });
$('#popClose').onclick = () => $('#scenarioPop').classList.remove('on');
$$('.switch').forEach(sw => sw.addEventListener('click', () => {
  sw.classList.toggle('on');
  sw.setAttribute('aria-checked', sw.classList.contains('on') ? 'true' : 'false');
}));
addEventListener('keydown', (e) => {
  if (e.key === 'Escape'){
    const tk = $('#takeover');
    if (tk.classList.contains('on')){                              // 取消当前接管
      if (state.scene === 'launching'){ seqToken++; state.scene = 'idle'; state.console = 'stopped'; tkClose(); paintUI(); }
      else if (state.scene !== 'portbusy'){ tkClose(); }
      return;
    }
    ['#themePop', '#setPop', '#scenarioPop'].forEach(p => $(p).classList.remove('on'));
  }
  if (e.key === 'Enter' && !e.target.closest('.pop') && e.target.tagName !== 'INPUT' && !$('#takeover').classList.contains('on')){
    e.preventDefault(); $('#btnPrimary').click();
  }
});

/* ---------- Toast ---------- */
function toast(tone, title, msg){
  const t = document.createElement('div'); t.className = 'toast';
  const led = document.createElement('span'); led.className = 'led ' + (tone === 'ok' ? 'ok' : tone === 'warn' ? 'warn' : 'err');
  const tx = document.createElement('div'); tx.className = 'tx';
  const tt = document.createElement('div'); tt.className = 'tt'; tt.textContent = title;
  tx.appendChild(tt);
  if (msg){ const m = document.createElement('div'); m.className = 'tm2'; m.textContent = msg; tx.appendChild(m); }
  t.appendChild(led); t.appendChild(tx);
  $('#toasts').appendChild(t);
  setTimeout(() => { t.classList.add('leaving'); setTimeout(() => t.remove(), 240); }, 3600);
}

/* ---------- 初始化 ---------- */
paintUI();
const __q = new URLSearchParams(location.search);
const __scene = __q.get('scene');
if (__scene && ['idle', 'launching', 'running', 'training', 'portbusy', 'firstrun', 'empty'].includes(__scene)) setScene(__scene);

/* 视口缩放（与 v1 相同的舞台适配） */
function fit(){
  const scale = Math.min(1, (innerWidth - 24) / 1400, (innerHeight - 24) / 880);
  $('#stageInner').style.transform = scale < 1 ? 'scale(' + scale + ')' : '';
}
addEventListener('resize', fit); fit();
console.log('[AYT launcher v2] ready');
</script>
</body>
</html>
"""

out = (T.replace("@@PREPAINT@@", PREPAINT)
        .replace("@@TOKENS@@", TOKENS)
        .replace("@@POPS@@", POPS)
        .replace("@@THEMECSS@@", THEMECSS)
        .replace("@@TOASTS@@", TOASTS)
        .replace("@@THEMEJS@@", THEMEJS))
io.open(DST, "w", encoding="utf-8", newline="").write(out)
print("written %s · %d chars · %d lines" % (DST, len(out), out.count("\n") + 1))
