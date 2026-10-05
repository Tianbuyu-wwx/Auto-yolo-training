// v6 冒烟：默认石墨 / 切玻璃 / 续训互斥 / 曲线 v2 / 控制台零错误
import { createRequire } from 'module';
const require = createRequire('C:/Users/Tianbuyu/AppData/Local/hermes/skills/creative/ui-craft-studio/package.json');
const { chromium } = require('playwright');
const URL = 'file:///E:/%E9%A1%B9%E7%9B%AE/Auto-yolo-training/tools/launcher-design/AYT-Launcher-v6.html';
const OUT = 'E:/项目/Auto-yolo-training/tools/launcher-design/_selfcheck/';
const results = [];
const ok = (n, c, x) => { results.push((c ? 'PASS  ' : 'FAIL  ') + n + (x ? '  :: ' + x : '')); };

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1560, height: 940 }, deviceScaleFactor: 2 });
const page = await ctx.newPage();
const errs = [];
page.on('pageerror', e => errs.push(String(e)));
page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });

// 1) 默认（石墨）
await page.goto(URL + '?t=' + Date.now(), { waitUntil: 'domcontentloaded' });
await page.evaluate(() => Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 3000))]));
await page.waitForTimeout(700);
ok('默认无 data-skin（石墨）', await page.evaluate(() => !document.documentElement.dataset.skin));
ok('默认氛围层隐藏', await page.evaluate(() => getComputedStyle(document.getElementById('atmo')).display === 'none'));
ok('默认水面引擎停（atmo off 类）', await page.evaluate(() => document.getElementById('atmo').classList.contains('off')));
ok('皮肤按钮默认=经典石墨', await page.evaluate(() => document.querySelector('#setSkin button[data-skin="graphite"]').classList.contains('on')));
await (await page.$('#stageInner')).screenshot({ path: OUT + 'v6-home-graphite.png' });

// 2) 切玻璃（设置页）
await page.click('.rit[data-page="settings"]'); await page.waitForTimeout(400);
await page.click('#setSkin button[data-skin="glass"]'); await page.waitForTimeout(700);
ok('切换后 data-skin=glass', await page.evaluate(() => document.documentElement.dataset.skin === 'glass'));
ok('氛围层显示', await page.evaluate(() => getComputedStyle(document.getElementById('atmo')).display !== 'none'));
ok('水面引擎运行（off 类移除）', await page.evaluate(() => !document.getElementById('atmo').classList.contains('off')));
const cvPx = await page.evaluate(() => new Promise(res => {
  setTimeout(() => {
    const c = document.getElementById('waterCv');
    const g = c.getContext('2d');
    const d = g.getImageData(0, 0, Math.min(64, c.width), Math.min(64, c.height)).data;
    let mx = 0; for (let i = 3; i < d.length; i += 4) mx = Math.max(mx, d[i]);
    res(mx);
  }, 1400);
}));
ok('水面画布有像素活动（maxA>0）', cvPx > 0, 'maxA=' + cvPx);
await page.click('.rit[data-page="home"]'); await page.waitForTimeout(600);
await page.mouse.move(400, 300); await page.waitForTimeout(120); await page.mouse.move(800, 420); await page.waitForTimeout(400);
await (await page.$('#stageInner')).screenshot({ path: OUT + 'v6-home-glass.png' });

// 3) 切回石墨复原
await page.click('.rit[data-page="settings"]'); await page.waitForTimeout(300);
await page.click('#setSkin button[data-skin="graphite"]'); await page.waitForTimeout(500);
ok('切回石墨后 skin 移除', await page.evaluate(() => !document.documentElement.dataset.skin));
ok('切回后氛围层隐藏', await page.evaluate(() => getComputedStyle(document.getElementById('atmo')).display === 'none'));

// 4) 续训互斥（config）
await page.click('.rit[data-page="config"]'); await page.waitForTimeout(600);
const before = await page.evaluate(() => {
  const sc = document.querySelector('#page-config .pscroll');
  return { scrollMax: sc.scrollHeight - sc.clientHeight, sumHid: document.getElementById('cfgSummary').hidden, boxHid: document.getElementById('cfgResumeBox').hidden };
});
ok('续训前：摘要显示/选择框隐藏', !before.sumHid && before.boxHid, JSON.stringify(before));
await page.click('#cfgResume'); await page.waitForTimeout(450);
const after = await page.evaluate(() => {
  const sc = document.querySelector('#cfg-config .pscroll') || document.querySelector('#page-config .pscroll');
  return { scrollMax: sc.scrollHeight - sc.clientHeight, sumHid: document.getElementById('cfgSummary').hidden, boxHid: document.getElementById('cfgResumeBox').hidden };
});
ok('续训后：选择框显示/摘要隐藏', after.boxHid === false && after.sumHid === true, JSON.stringify(after));
ok('续训前后零高度增长（scrollMax 不变）', before.scrollMax === after.scrollMax, before.scrollMax + ' → ' + after.scrollMax);
await (await page.$('#stageInner')).screenshot({ path: OUT + 'v6-config-resume.png' });
await page.click('#cfgResume'); await page.waitForTimeout(400);
ok('再关：恢复摘要', await page.evaluate(() => document.getElementById('cfgSummary').hidden === false && document.getElementById('cfgResumeBox').hidden === true));

// 5) 曲线 v2（monitor）
await page.click('.rit[data-page="monitor"]'); await page.waitForTimeout(400);
await page.click('#scenarioBtn'); await page.waitForTimeout(150);
await page.click('#scenarioPop .pop-i[data-scene="training"]'); await page.waitForTimeout(700);
const chk = await page.evaluate(() => {
  const cl = document.querySelector('#chartLoss svg');
  const cm = document.querySelector('#chartMap svg');
  const q = (el, sel) => el ? el.querySelectorAll(sel).length : -1;
  return {
    lossPath: q(cl, 'path[fill="none"]'), lossArea: q(cl, 'path[fill^="url("]'),
    mapPath: q(cm, 'path[fill="none"]'), mapArea: q(cm, 'path[fill^="url("]'),
    legend: q(cm, 'text'),
    xs: [...(cm ? cm.querySelectorAll('text') : [])].map(t => t.textContent).filter(t => /^E\d/.test(t)).length,
    liveDot: q(cm, '.live-dot'),
    hoverEls: q(cm, '.hover-guide'),
    smooth: q(cl, 'path[fill="none"]') > 0 && (cl.querySelector('path[fill="none"]').getAttribute('d') || '').includes('C'),
  };
});
ok('loss 图：平滑路径 + 面积', chk.lossPath >= 1 && chk.lossArea >= 1 && chk.smooth, JSON.stringify(chk));
ok('map 图：双线 + 图例 + X 轴 + live-dot + hover', chk.mapPath === 2 && chk.liveDot === 1 && chk.hoverEls >= 4 && chk.xs >= 3, JSON.stringify(chk));
// hover 交互
await page.hover('#chartMap svg', { position: { x: 300, y: 60 } }); await page.waitForTimeout(200);
ok('hover 引导可见', await page.evaluate(() => {
  const g = document.querySelector('#chartMap .hover-guide[visibility="visible"]');
  return !!g;
}));
await (await page.$('#stageInner')).screenshot({ path: OUT + 'v6-monitor.png' });

// 6) 控制台
ok('零控制台错误', errs.length === 0, errs.slice(0, 3).join(' | '));

console.log(results.join('\n'));
const fails = results.filter(r => r.startsWith('FAIL')).length;
console.log('===== SMOKE: ' + (fails ? fails + ' FAIL' : 'ALL PASS') + ' =====');
await browser.close();
