// 浅色玻璃日志 + 续训组件检测：4 组合 × 开/关，文字越界/越界/重叠 + 截图
import { createRequire } from 'module';
const require = createRequire('C:/Users/Tianbuyu/AppData/Local/hermes/skills/creative/ui-craft-studio/package.json');
const { chromium } = require('playwright');
const URL = 'file:///E:/%E9%A1%B9%E7%9B%AE/Auto-yolo-training/tools/launcher-design/AYT-Launcher-v8.html?page=config#';
const OUT = 'E:/项目/Auto-yolo-training/tools/launcher-design/_selfcheck/';

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, headless: true });
const combos = [
  { name: 'graphite-dark', skin: null, mode: 'dark' },
  { name: 'graphite-light', skin: null, mode: 'light' },
  { name: 'glass-dark', skin: 'glass', mode: 'dark' },
  { name: 'glass-light', skin: 'glass', mode: 'light' },
];

const inspect = () => {
  const exec = document.getElementById('cfgExec');
  const er = exec.getBoundingClientRect();
  const vis = el => { const st = getComputedStyle(el); return st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0'; };
  const out = { overflow: [], outOfBounds: [], overlaps: [], logBg: '' };
  const logEl = document.querySelector('#page-monitor .log');
  if (logEl) out.logBg = getComputedStyle(logEl).backgroundColor;
  exec.querySelectorAll('*').forEach(el => {
    if (!(el instanceof HTMLElement) || !vis(el)) return;
    if (el.tagName === 'SELECT' && el.closest('.dd')) return;
    const st = getComputedStyle(el);
    if (st.textOverflow === 'ellipsis' && st.overflow === 'hidden') return;   // 有意省略号截断
    if (el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 2){
      out.overflow.push({ id: el.id, cls: String(el.className).slice(0, 44), sw: el.scrollWidth, cw: el.clientWidth, txt: (el.textContent || '').trim().slice(0, 58) });
    }
  });
  exec.querySelectorAll('*').forEach(el => {
    if (!(el instanceof HTMLElement) || !vis(el)) return;
    if (el.tagName === 'SELECT' && el.closest('.dd')) return;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return;
    if (r.right > er.right + 0.8 || r.left < er.left - 0.8){
      out.outOfBounds.push({ id: el.id, cls: String(el.className).slice(0, 44), l: Math.round(r.left), rgt: Math.round(r.right), erl: Math.round(er.left), err_: Math.round(er.right) });
    }
  });
  const cands = [...exec.querySelectorAll('.rtxt, .dd, .ce-sum, .btn, .chk, .cc-hint, .ce-row, .cc-row, .switch')]
    .filter(el => vis(el) && getComputedStyle(el).position !== 'absolute')
    .map(el => ({ el, r: el.getBoundingClientRect(), key: (String(el.className).split(' ')[0] || '') + (el.id ? '#' + el.id : '') }));
  for (let i = 0; i < cands.length; i++) for (let j = i + 1; j < cands.length; j++){
    const a = cands[i], b = cands[j];
    if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
    const x = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left);
    const y = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
    if (x > 1 && y > 1 && x * y > 6) out.overlaps.push({ a: a.key, b: b.key, area: Math.round(x * y) });
  }
  return out;
};

for (const c of combos){
  const ctx = await browser.newContext({ viewport: { width: 1560, height: 940 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  await page.addInitScript(({ sk, md }) => {
    if (sk) localStorage.setItem('ayt.skin', 'glass');
    localStorage.setItem('ayt.theme', JSON.stringify({ mode: md, accent: 'brass' }));
  }, { sk: c.skin, md: c.mode });
  await page.goto(URL + '&t=' + Date.now(), { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 3000))]));
  await page.waitForTimeout(650);

  const off = await page.evaluate(inspect);
  await page.click('#cfgResume'); await page.waitForTimeout(460);
  const on = await page.evaluate(inspect);
  await (await page.$('#stageInner')).screenshot({ path: OUT + 'v9-' + c.name + '-resume.png' });

  // 监控页日志背景（各组合都看一眼）
  await page.click('.rit[data-page="monitor"]'); await page.waitForTimeout(420);
  const mon = await page.evaluate(inspect);

  console.log('## ' + c.name);
  console.log('  续训关: 溢出=' + off.overflow.length + ' 越界=' + off.outOfBounds.length + ' 重叠=' + off.overlaps.length);
  if (off.overflow.length) console.log('   溢出:', JSON.stringify(off.overflow.slice(0, 5)));
  if (off.outOfBounds.length) console.log('   越界:', JSON.stringify(off.outOfBounds.slice(0, 5)));
  if (off.overlaps.length) console.log('   重叠:', JSON.stringify(off.overlaps.slice(0, 6)));
  console.log('  续训开: 溢出=' + on.overflow.length + ' 越界=' + on.outOfBounds.length + ' 重叠=' + on.overlaps.length);
  if (on.overflow.length) console.log('   溢出:', JSON.stringify(on.overflow.slice(0, 5)));
  if (on.outOfBounds.length) console.log('   越界:', JSON.stringify(on.outOfBounds.slice(0, 5)));
  if (on.overlaps.length) console.log('   重叠:', JSON.stringify(on.overlaps.slice(0, 6)));
  await ctx.close();
}
// 浅色玻璃监控页日志背景单拍
const ctx2 = await browser.newContext({ viewport: { width: 1560, height: 940 }, deviceScaleFactor: 2 });
const p2 = await ctx2.newPage();
await p2.addInitScript(() => { localStorage.setItem('ayt.skin', 'glass'); localStorage.setItem('ayt.theme', JSON.stringify({ mode: 'light', accent: 'brass' })); });
await p2.goto('file:///E:/%E9%A1%B9%E7%9B%AE/Auto-yolo-training/tools/launcher-design/AYT-Launcher-v8.html?page=monitor&scene=training#&t=' + Date.now(), { waitUntil: 'domcontentloaded' });
await p2.evaluate(() => Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 3000))]));
await p2.waitForTimeout(700);
const bg = await p2.evaluate(() => getComputedStyle(document.querySelector('#page-monitor .log')).backgroundColor);
console.log('## 浅色玻璃 · 监控日志背景色 =', bg);
await (await p2.$('#stageInner')).screenshot({ path: OUT + 'v9-glass-light-monitor.png' });
await ctx2.close();
await browser.close();
