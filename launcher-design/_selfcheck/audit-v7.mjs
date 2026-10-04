// AYT 启动器 v4 · 深度审计（程序 + 视觉量化）
// 检查：控制台错误 / CSS 变量缺失 / SVG symbol 缺失 / 文字溢出 / 越界 / 卡片重叠 /
//       吸底卡遮挡 / onclick 函数缺失 / 死链 / @@ 残留 / 卡片对齐分布 / 滚动到底复检
// 运行（任意目录免拷贝）：CHROME_PATH=… node audit-v4.mjs
import { createRequire } from 'module';
const require = createRequire('C:/Users/Tianbuyu/AppData/Local/hermes/skills/creative/ui-craft-studio/package.json');
const { chromium } = require('playwright');
import { writeFileSync } from 'fs';

const URL = 'file:///E:/%E9%A1%B9%E7%9B%AE/Auto-yolo-training/launcher-design/AYT-Launcher-v7.html';
const OUT = 'E:/项目/Auto-yolo-training/launcher-design/_selfcheck/audit-v7-report.json';
const PAGES = ['home', 'datasets', 'config', 'monitor', 'results', 'registry', 'queue', 'checkup', 'settings'];
const report = [];

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1560, height: 940 } });
const page = await ctx.newPage();
const errs = [];
page.on('pageerror', e => errs.push('pageerror: ' + String(e)));
page.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text()); });

async function goto(suffix){
  await page.goto(URL + '?t=' + Date.now() + (suffix || '').replace(/^\?/, '&'), { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 3000))]));
  await page.waitForTimeout(520);
}

/* ---------- 通用探针（在 .page.on 范围内） ---------- */
async function probe(name){
  const r = await page.evaluate(() => {
    const res = {};
    const active = document.querySelector('.page.on');
    const win = document.getElementById('win').getBoundingClientRect();
    const stage = document.getElementById('stageInner').getBoundingClientRect();

    /* 1. @@ 残留 */
    res.placeholders = (document.documentElement.innerHTML.match(/@@[A-Z_]+@@/g) || []).slice(0, 5);

    /* 2. 文字溢出 */
    res.overflows = [];
    document.querySelectorAll('.page.on *').forEach(el => {
      if (!(el instanceof HTMLElement)) return;
      const st = getComputedStyle(el);
      if (st.display === 'none' || st.visibility === 'hidden') return;
      if (el.closest('.log') || el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') return;   // 日志天然滚动
      if (st.textOverflow === 'ellipsis' && st.overflow === 'hidden') return;                  // 有意省略号截断
      if (el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 2){
        const txt = (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 42);
        res.overflows.push({ cls: String(el.className).slice(0, 48), id: el.id, sw: el.scrollWidth, cw: el.clientWidth, ov: st.overflow + '/' + st.overflowX, txt });
      }
    });
    res.overflows = res.overflows.slice(0, 25);

    /* 3. 越界（对比 stageInner 可视区） */
    res.outOfBounds = [];
    document.querySelectorAll('.page.on *').forEach(el => {
      if (!(el instanceof HTMLElement)) return;
      if (el.tagName === 'svg' || el.ownerSVGElement) return;
      const st = getComputedStyle(el);
      if (st.display === 'none' || st.visibility === 'hidden') return;
      const rr = el.getBoundingClientRect();
      if (rr.width < 2 || rr.height < 2) return;
      if (rr.right > stage.right + 1.5 || rr.left < stage.left - 1.5){
        res.outOfBounds.push({ cls: String(el.className).slice(0, 48), id: el.id, l: Math.round(rr.left), rgt: Math.round(rr.right), stageR: Math.round(stage.right) });
      }
    });
    res.outOfBounds = res.outOfBounds.slice(0, 20);

    /* 4. 卡片级重叠（静态定位、非同族父子） */
    const els = [...document.querySelectorAll('.page.on .card, .page.on .panel, .page.on .pcard, .page.on .stat, .page.on .jrow, .page.on .trow, .page.on .row, .page.on .warnbanner, .page.on .empty-state, .page.on .status-hero, .page.on .hero-actions')]
      .filter(el => {
        const st = getComputedStyle(el);
        if (st.display === 'none' || st.visibility === 'hidden' || +st.opacity < 0.05) return false;
        if (st.position === 'absolute' || st.position === 'fixed' || st.position === 'sticky') return false;
        const rr = el.getBoundingClientRect();
        return rr.width > 6 && rr.height > 6;
      })
      .map(el => ({ el, rr: el.getBoundingClientRect(), key: (el.className && String(el.className).split(' ')[0]) + (el.id ? '#' + el.id : '') }));
    res.overlaps = [];
    for (let i = 0; i < els.length; i++) for (let j = i + 1; j < els.length; j++){
      const a = els[i], b = els[j];
      if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
      const x = Math.min(a.rr.right, b.rr.right) - Math.max(a.rr.left, b.rr.left);
      const y = Math.min(a.rr.bottom, b.rr.bottom) - Math.max(a.rr.top, b.rr.top);
      if (x > 2 && y > 2 && x * y > 30){
        res.overlaps.push({ a: a.key, b: b.key, area: Math.round(x * y), ay: Math.round(a.rr.top), by: Math.round(b.rr.top) });
      }
    }
    res.overlaps = res.overlaps.slice(0, 15);

    /* 5. 卡片对齐分布（left 采样） */
    const lefts = {};
    document.querySelectorAll('.page.on .card, .page.on .panel, .page.on .pcard').forEach(el => {
      const st = getComputedStyle(el);
      if (st.display === 'none') return;
      const k = Math.round(el.getBoundingClientRect().left);
      lefts[k] = (lefts[k] || 0) + 1;
    });
    res.lefts = lefts;

    /* 6. onclick 函数缺失 */
    const names = new Set();
    document.querySelectorAll('.page.on [onclick], [onclick]').forEach(el => {
      (el.getAttribute('onclick') || '').replace(/([A-Za-z_$][\w$]*)\s*\(/g, (m, g) => { names.add(g); return m; });
    });
    res.missingFns = [...names].filter(n => n !== 'event' && typeof window[n] !== 'function');

    /* 7. 死链统计 */
    res.deadLinks = document.querySelectorAll('.page.on a[href="#"], .page.on a:not([href])').length;
    return res;
  });
  report.push({ type: 'page', name, ...r });
  const bad = (r.overflows.length + r.outOfBounds.length + r.overlaps.length + r.missingFns.length + r.placeholders.length);
  console.log(`[${name}] 溢出=${r.overflows.length} 越界=${r.outOfBounds.length} 重叠=${r.overlaps.length} 缺函数=${r.missingFns.length} 死链=${r.deadLinks} lefts=${JSON.stringify(r.lefts)} ${bad ? '⚠' : '✓'}`);
  if (r.overflows.length) console.log('   溢出:', JSON.stringify(r.overflows.slice(0, 6)));
  if (r.outOfBounds.length) console.log('   越界:', JSON.stringify(r.outOfBounds.slice(0, 6)));
  if (r.overlaps.length) console.log('   重叠:', JSON.stringify(r.overlaps.slice(0, 6)));
  if (r.missingFns.length) console.log('   缺函数:', r.missingFns.join(', '));
}

/* ---------- 全局检查 ---------- */
await goto('');
const global = await page.evaluate(() => {
  const cssText = [...document.querySelectorAll('style')].map(s => s.textContent).join('\n');
  const defs = new Set();
  (cssText.matchAll(/--([a-zA-Z0-9_-]+)\s*:/g) || []);
  for (const m of cssText.matchAll(/--([a-zA-Z0-9_-]+)\s*:/g)) defs.add(m[1]);
  const refs = new Set();
  for (const m of cssText.matchAll(/var\(\s*--([a-zA-Z0-9_-]+)/g)) refs.add(m[1]);
  const missingVars = [...refs].filter(x => !defs.has(x));
  const unusedVars = [...defs].filter(x => !refs.has(x) && !/^(accent|bg|ink|t-|r-|sp|fs)/.test(x));
  const syms = new Set([...document.querySelectorAll('symbol[id]')].map(s => s.id));
  const uses = new Set();
  document.querySelectorAll('use').forEach(u => { const h = (u.getAttribute('href') || u.getAttribute('xlink:href') || '').replace('#', ''); if (h) uses.add(h); });
  return {
    missingVars, unusedVars: [...defs].filter(x => !refs.has(x) && !/^(accent|bg|ink|t-|r-|sp|fs)/.test(x)),
    missingSymbols: [...uses].filter(u => !syms.has(u)),
    unusedSymbols: [...syms].filter(s => !uses.has(s)),
    title: document.title
  };
});
report.push({ type: 'global', ...global });
console.log('\n== 全局 ==');
console.log('CSS 未定义变量:', global.missingVars.length ? global.missingVars.join(', ') : '无');
console.log('SVG 缺失 symbol:', global.missingSymbols.length ? global.missingSymbols.join(', ') : '无');
console.log('未使用 symbol 数:', global.unusedSymbols.length, '| 未使用变量(非主题类):', global.unusedVars.join(', ') || '无');

/* ---------- 逐页探针 ---------- */
console.log('\n== 逐页 ==');
for (const p of PAGES){
  await goto('?page=' + p + '#');
  await probe(p);
}

/* ---------- 场景态（首页） ---------- */
console.log('\n== 场景态 ==');
for (const sc of ['firstrun', 'portbusy', 'training']){
  await goto('');
  await page.click('#scenarioBtn'); await page.waitForTimeout(160);
  await page.click(`#scenarioPop .pop-i[data-scene="${sc}"]`); await page.waitForTimeout(360);
  await page.click('.rit[data-page="home"]'); await page.waitForTimeout(420);
  await probe('home@' + sc);
}

/* ---------- config 专家态 ---------- */
await goto('?page=config&expert=1#');
await probe('config@expert');

/* ---------- 吸底卡遮挡专项（config） ---------- */
await goto('?page=config#');
const occl = await page.evaluate(async () => {
  const sc = document.querySelector('#page-config .pscroll');
  if (!sc) return { err: 'no pscroll' };
  sc.scrollTop = sc.scrollHeight;
  await new Promise(r => setTimeout(r, 420));
  const cards = [...sc.querySelectorAll('.card, .panel, .pcard')].filter(el => {
    if (el.id === 'cfgExec') return false;                                  // sticky 卡自身不计
    const st = getComputedStyle(el);
    if (st.position === 'sticky' || st.position === 'fixed') return false;  // 吸底/悬浮卡不计
    const rr = el.getBoundingClientRect();
    return st.display !== 'none' && rr.height > 8;
  });
  const exec = document.querySelector('#cfgExec');
  if (!exec || !cards.length) return { err: 'no exec/cards' };
  const ex = exec.getBoundingClientRect();
  const last = cards[cards.length - 1];
  const lr = last.getBoundingClientRect();
  const execPos = getComputedStyle(exec).position;
  /* 内容底 padding 是否把最后卡托出遮挡区 */
  const padB = parseFloat(getComputedStyle(sc).paddingBottom || '0');
  return {
    execPos, execTop: Math.round(ex.top), lastCardBottom: Math.round(lr.bottom),
    gap: Math.round(ex.top - lr.bottom), padB,
    overlapPx: Math.max(0, Math.round(lr.bottom - ex.top))
  };
});
report.push({ type: 'sticky-occlusion', ...occl });
console.log('\n== 吸底卡遮挡专项（config 滚到底）==');
console.log(JSON.stringify(occl));

/* ---------- 控制台错误 ---------- */
console.log('\n== 控制台错误 ==');
console.log(errs.length ? errs.slice(0, 8).join('\n') : '无（全程 0 错误）');

writeFileSync(OUT, JSON.stringify({ report, errs }, null, 1), 'utf8');
console.log('\nJSON ->', OUT);
await browser.close();
