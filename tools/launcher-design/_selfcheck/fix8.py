# -*- coding: utf-8 -*-
"""fix8：主题系统 UI + 引擎（标题栏弹层 / 设置页外观组 / JS 状态机与持久化）"""
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

# ---------- 1. 标题栏「外观」按钮 ----------
rep('<div class="wctl">',
'''<button class="tb-scene tb-theme" id="themeBtn" type="button" aria-haspopup="true" title="外观">
          <svg viewBox="0 0 12 12" fill="none"><circle cx="6" cy="6" r="4.4" stroke="currentColor" stroke-width="1.1"/><path d="M6 1.6a4.4 4.4 0 0 1 0 8.8Z" fill="currentColor" opacity=".5"/></svg>
          外观
        </button>
        <div class="wctl">''', 1, "titlebar-btn")

# ---------- 2. 主题弹层 ----------
SWATCH = '''<button type="button" class="sw-brass" data-accent="brass" title="鎏金" aria-label="强调色：鎏金"></button>
          <button type="button" class="sw-celadon" data-accent="celadon" title="青瓷" aria-label="强调色：青瓷"></button>
          <button type="button" class="sw-indigo" data-accent="indigo" title="靛蓝" aria-label="强调色：靛蓝"></button>
          <button type="button" class="sw-ink" data-accent="ink" title="砚墨" aria-label="强调色：砚墨"></button>
          <button type="button" class="tcustom" data-accent="custom" title="自定义…" aria-label="自定义强调色"><input type="color" IDPLACE value="#c9a35c" tabindex="-1" aria-hidden="true" /></button>'''

rep('    <div class="ctx" id="ctxMenu"></div>',
'''    <div class="pop" id="themePop">
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
          ''' + SWATCH.replace(' IDPLACE', ' id="tpColor"') + '''
        </div>
      </div>
      <div class="tfoot">自定义色按对比度自动配字色 · <a href="#settings" data-nav="settings">设置 → 外观</a></div>
    </div>

    <div class="ctx" id="ctxMenu"></div>''', 1, "theme-popover")

# ---------- 3. 设置页「外观」组 ----------
rep('          <div class="setwrap">\n            <div class="sgroup">\n              <div class="sgroup-h"><span class="micro">启动行为 · LAUNCH</span></div>',
'''          <div class="setwrap">
            <div class="sgroup">
              <div class="sgroup-h"><span class="micro">外观 · APPEARANCE</span></div>
              <div class="srow">
                <div class="sl"><div class="sn">主题模式</div><div class="sd">深色 / 浅色 / 跟随系统（跟随 Windows 的浅色·深色设置）。</div></div>
                <div class="sctrl"><div class="tseg" id="setMode">
                  <button type="button" data-mode="dark">深色</button>
                  <button type="button" data-mode="light">浅色</button>
                  <button type="button" data-mode="system">跟随系统</button>
                </div></div>
              </div>
              <div class="srow">
                <div class="sl"><div class="sn">强调色</div><div class="sd">用于主操作、选中与活动指示灯；自定义色自动配字色。</div></div>
                <div class="sctrl"><div class="tsw" id="setAcc">
                  ''' + SWATCH.replace(' IDPLACE', ' id="setColor"') + '''
                </div></div>
              </div>
            </div>

            <div class="sgroup">
              <div class="sgroup-h"><span class="micro">启动行为 · LAUNCH</span></div>''', 1, "settings-appearance")

# ---------- 4. CSS ----------
rep('/* __CSS_MORE__ */',
'''/* ==========================================================================
   §T 外观 / 主题控件
   ========================================================================== */
.tb-theme{ margin-right:8px; }
.tb-theme svg{ width:11px; height:11px; }
.pop .trow{ display:flex; align-items:center; gap:10px; padding:8px 10px 6px; }
.pop .trow-l{ width:48px; flex-shrink:0; font-size:12px; color:var(--ink3); }
.tseg{ display:inline-flex; border:1px solid var(--line2); border-radius:10px; overflow:hidden; background:var(--bg-deep); }
.tseg button{ height:26px; padding:0 10px; border:0; background:transparent; color:var(--ink3); font-size:12px; font-family:var(--f-sans); cursor:pointer; white-space:nowrap;
  transition:background var(--t-fast) var(--e-io), color var(--t-fast) var(--e-io); }
.tseg button + button{ border-left:1px solid var(--line); }
.tseg button:hover{ color:var(--ink); }
.tseg button.on{ background:var(--bg-raise); color:var(--ink); }
.tsw{ display:flex; gap:9px; align-items:center; }
.tsw button{ width:22px; height:22px; flex-shrink:0; border-radius:999px; border:1px solid var(--line2); cursor:pointer; padding:0;
  transition:outline-color var(--t-fast) var(--e-io), transform var(--t-fast) var(--e-io); outline:2px solid transparent; outline-offset:2px; }
.tsw button:hover{ transform:translateY(-1px); }
.tsw button.on{ outline-color:rgba(var(--acc-rgb),.85); }
.sw-brass{ background:linear-gradient(135deg,#d8b872,#b08a3e); }
.sw-celadon{ background:linear-gradient(135deg,#8fb9a6,#4b7a62); }
.sw-indigo{ background:linear-gradient(135deg,#96a5dd,#5a6cb0); }
.sw-ink{ background:linear-gradient(135deg,#b8ae9c,#6d6455); }
.tsw .tcustom{ position:relative; overflow:hidden; background:conic-gradient(from 30deg, #c9a35c, #7fa895, #8291cf, #cbc2b1, #c9a35c); }
.tsw .tcustom input{ position:absolute; inset:0; width:100%; height:100%; opacity:0; border:0; padding:0; cursor:pointer; }
.pop .tfoot{ margin:6px 10px 6px; padding-top:9px; border-top:1px solid var(--line); font-size:12px; color:var(--ink3); line-height:1.6; }
.pop .tfoot a{ color:var(--acc-text); text-decoration:none; }
.pop .tfoot a:hover{ text-decoration:underline; }
/* 切换瞬间的全局过渡（仅 260ms；reduced-motion 关闭） */
html.theming, html.theming *, html.theming *::before, html.theming *::after{
  transition:background-color .22s ease, border-color .22s ease, color .22s ease, box-shadow .22s ease !important;
}
@media (prefers-reduced-motion: reduce){ html.theming, html.theming *{ transition:none !important; } }

/* __CSS_MORE__ */''', 1, "css-block")

# ---------- 5. JS 引擎 ----------
JS = '''/* ---------- 主题系统 ---------- */
const THEME_KEY = 'ayt.theme';
const themeState = (() => {
  let st = {};
  try { st = JSON.parse(localStorage.getItem(THEME_KEY) || '{}'); } catch (_) {}
  return {
    mode: st.mode || document.documentElement.dataset.modePref || 'dark',
    accent: st.accent || document.documentElement.dataset.accent || 'brass',
    custom: st.custom || '#c9a35c',
    cc: st.cc || null,
  };
})();
const sysLightMQ = matchMedia('(prefers-color-scheme: light)');
function tHex2rgb(h){ h = h.replace('#',''); if (h.length === 3) h = h.split('').map(c => c + c).join(''); return [parseInt(h.slice(0,2),16), parseInt(h.slice(2,4),16), parseInt(h.slice(4,6),16)]; }
function tLum(rgb){ const f = c => { c /= 255; return c <= .03928 ? c/12.92 : Math.pow((c + .055)/1.055, 2.4); }; return .2126*f(rgb[0]) + .7152*f(rgb[1]) + .0722*f(rgb[2]); }
function tMix(a, b, t){ return a.map((v, i) => Math.round(v + (b[i] - v) * t)); }
function tHex(rgb){ return '#' + rgb.map(v => v.toString(16).padStart(2,'0')).join(''); }
function tRatio(l1, l2){ const hi = l1 > l2 ? l1 : l2, lo = l1 > l2 ? l2 : l1; return (hi + .05) / (lo + .05); }
function tDeriveCustom(hexIn, mode){
  const base = tHex2rgb(hexIn);
  const hi = tMix(base, [255,255,255], mode === 'light' ? .30 : .35);
  const lo = tMix(base, [0,0,0], .32);
  const card = mode === 'light' ? [247,243,236] : [26,23,21];
  let textRgb = mode === 'light' ? tMix(base, [0,0,0], .10) : base.slice();
  if (mode === 'light'){ let t = .10; while (t < .9 && tRatio(tLum(textRgb), tLum(card)) < 4.55){ t += .05; textRgb = tMix(base, [0,0,0], t); } }
  const onAcc = tLum(base) > .40 ? '#241a08' : '#f8f4ec';
  return { 'acc': tHex(base), 'acc-rgb': base.join(','), 'acc-hi': tHex(hi), 'acc-hi-rgb': hi.join(','), 'acc-lo': tHex(lo), 'acc-text': tHex(textRgb), 'on-acc': onAcc };
}
function applyTheme(persist = true){
  const d = document.documentElement;
  const resolved = themeState.mode === 'system' ? (sysLightMQ.matches ? 'light' : 'dark') : themeState.mode;
  d.dataset.mode = resolved;
  d.dataset.modePref = themeState.mode;
  d.dataset.accent = themeState.accent;
  const cm = document.querySelector('meta[name="color-scheme"]');
  if (cm) cm.setAttribute('content', resolved === 'light' ? 'light dark' : 'dark light');
  ['acc','acc-rgb','acc-hi','acc-hi-rgb','acc-lo','acc-text','on-acc'].forEach(k => d.style.removeProperty('--' + k));
  if (themeState.accent === 'custom'){
    const v = tDeriveCustom(themeState.custom, resolved);
    themeState.cc = v;
    Object.keys(v).forEach(k => d.style.setProperty('--' + k, v[k]));
  }
  if (persist){ try { localStorage.setItem(THEME_KEY, JSON.stringify(themeState)); } catch (_) {} }
  $$('#tpMode button, #setMode button').forEach(b => b.classList.toggle('on', b.dataset.mode === themeState.mode));
  $$('#tpAcc button, #setAcc button').forEach(b => b.classList.toggle('on', b.dataset.accent === themeState.accent));
  ['#tpColor','#setColor'].forEach(sel => { const el = $(sel); if (el) el.value = /^#[0-9a-fA-F]{6}$/.test(themeState.custom) ? themeState.custom : '#c9a35c'; });
}
function switchTheme(then){ document.documentElement.classList.add('theming'); then(); setTimeout(() => document.documentElement.classList.remove('theming'), RM ? 0 : 260); }
function setThemeMode(m){ if (m === themeState.mode) return; switchTheme(() => { themeState.mode = m; applyTheme(); }); }
function setThemeAccent(a){ if (a === themeState.accent && a !== 'custom') return; switchTheme(() => { themeState.accent = a; applyTheme(); }); }
sysLightMQ.addEventListener('change', () => { if (themeState.mode === 'system') applyTheme(); });
$('#themeBtn').onclick = (e) => { e.stopPropagation(); $('#scenarioPop').classList.remove('on'); $('#themePop').classList.toggle('on'); };
addEventListener('click', (e) => { if (!e.target.closest('#themePop') && !e.target.closest('#themeBtn')) $('#themePop').classList.remove('on'); });
$('#themePop').addEventListener('click', (e) => { if (e.target.closest('[data-nav]')) $('#themePop').classList.remove('on'); });
$$('#tpMode button, #setMode button').forEach(b => b.onclick = () => setThemeMode(b.dataset.mode));
$$('#tpAcc button[data-accent], #setAcc button[data-accent]').forEach(b => b.onclick = (e) => {
  if (b.dataset.accent === 'custom'){ if (e.target && e.target.tagName === 'INPUT') return; const inp = b.querySelector('input'); if (inp) inp.click(); }
  else setThemeAccent(b.dataset.accent);
});
['#tpColor','#setColor'].forEach(sel => { const el = $(sel); if (!el) return;
  el.addEventListener('input', () => { themeState.custom = el.value; themeState.accent = 'custom'; switchTheme(applyTheme); });
  el.addEventListener('change', () => { try { localStorage.setItem(THEME_KEY, JSON.stringify(themeState)); } catch (_) {} });
});
applyTheme(false);

/* ---------- 初始化 ---------- */'''
rep('/* ---------- 初始化 ---------- */', JS, 1, "js-engine")

# ---------- 6. 两个既有弹层与其互斥 ----------
rep('$(\'#scenarioBtn\').onclick = (e) => { e.stopPropagation(); $(\'#scenarioPop\').classList.toggle(\'on\'); };',
    '$(\'#scenarioBtn\').onclick = (e) => { e.stopPropagation(); $(\'#themePop\').classList.remove(\'on\'); $(\'#scenarioPop\').classList.toggle(\'on\'); };', 1, "scenario-btn-excl")
rep("    $('#scenarioPop').classList.remove('on'); ctx.classList.remove('on');",
    "    $('#scenarioPop').classList.remove('on'); $('#themePop').classList.remove('on'); ctx.classList.remove('on');", 1, "esc-close")

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("OK fix8 applied")
