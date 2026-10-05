// AYT 启动器原型 · 程序化审查（Playwright）
// 检查：控制台错误 / 字体真实加载（字宽对比法）/ 溢出断言 / 关键交互 / 逐屏截图
// 运行：复制到 ui-craft-studio skill 目录（其 node_modules 内有 playwright）后执行：
//   cd <skill目录> && node check-prototype.mjs
// （ESM 解析不走 NODE_PATH，脚本必须物理位于有 node_modules 的目录旁）
import { chromium } from 'playwright';
import { pathToFileURL } from 'url';

const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const FILE = 'E:/项目/Auto-yolo-training/tools/launcher-design/AYT-Launcher-v1.html';
const OUT = 'E:/项目/Auto-yolo-training/tools/launcher-design/_selfcheck';
const base = pathToFileURL(FILE).href;
let vc = 0;
const u = (hash, scene) => base + '?v=' + (++vc) + (scene ? '&scene=' + scene : '') + (hash ? '#' + hash : '');

const browser = await chromium.launch({ executablePath: EDGE, headless: true });
const page = await browser.newPage({ viewport: { width: 1560, height: 940 }, deviceScaleFactor: 2 });

const errors = [];
page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));
page.on('console', m => { if (m.type() === 'error') errors.push('CONSOLE: ' + m.text()); });
page.on('requestfailed', r => errors.push('REQFAIL: ' + r.url().slice(0, 110)));

const results = [];
function ok(name, cond, extra = '') { results.push((cond ? 'PASS' : 'FAIL') + '  ' + name + (extra ? '  :: ' + extra : '')); }

async function load(url, settle = 900) {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.evaluate(() => Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 4000))]));
  await page.waitForTimeout(settle);
}

async function fontCheck() {
  return await page.evaluate(async () => {
    const cases = [
      ['Instrument Serif', 'AutoYOLO Training'],
      ['Instrument Sans Variable', 'AutoYOLO Training 123'],
      ['IBM Plex Mono', '127.0.0.1:8080 mAP@50'],
      ['Noto Sans SC', '启动台 训练配置 数据集'],
      ['Noto Serif SC', '未启动 · 环境就绪'],
    ];
    const el = document.createElement('span');
    el.style.cssText = 'position:absolute;visibility:hidden;font-size:40px;white-space:nowrap';
    document.body.appendChild(el);
    const out = {};
    for (const [f, text] of cases) {
      try { await document.fonts.load('40px "' + f + '"', text); } catch (e) {}
      el.style.fontFamily = '"' + f + '", monospace';
      el.textContent = text;
      const w1 = el.getBoundingClientRect().width;
      el.style.fontFamily = 'monospace';
      const w2 = el.getBoundingClientRect().width;
      out[f] = { loaded: Math.abs(w1 - w2) > 0.5, w1: +w1.toFixed(1), w2: +w2.toFixed(1) };
    }
    el.remove();
    return out;
  });
}

async function overflowCheck() {
  return await page.evaluate(() => {
    const win = document.querySelector('#win').getBoundingClientRect();
    const bad = [];
    document.querySelectorAll('#win *').forEach(el => {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) return;
      if (r.right > win.right + 0.5 || r.left < win.left - 0.5) {
        let p = el.parentElement, skip = false;
        while (p && p !== document.body) {
          const o = getComputedStyle(p);
          if (/(auto|scroll)/.test(o.overflowX)) { skip = true; break; }
          p = p.parentElement;
        }
        if (!skip) bad.push((el.className + '').toString().slice(0, 46) + ' <' + el.tagName + '> dRight=' + Math.round(r.right - win.right) + ' dLeft=' + Math.round(r.left - win.left));
      }
    });
    return bad.slice(0, 10);
  });
}

async function textClipCheck() {
  // 表格单元格截断检查（scrollWidth 明显大于 clientWidth 的 td）
  return await page.evaluate(() => {
    const bad = [];
    document.querySelectorAll('#win td, #win .erow .ev, #win .svc-head .ep').forEach(el => {
      if (el.scrollWidth > el.clientWidth + 2 && el.clientWidth > 0) {
        bad.push((el.textContent + '').trim().slice(0, 34) + ' [' + el.clientWidth + '<' + el.scrollWidth + ']');
      }
    });
    return bad.slice(0, 12);
  });
}

async function shotWin(name) {
  const el = await page.$('#stageInner');
  await el.screenshot({ path: OUT + '/final-' + name + '.png' });
}

// ---------- 1. 逐屏 / 逐场景截图 + 检查 ----------
const screens = [
  ['home', u('home')],
  ['services', u('services')],
  ['env', u('env')],
  ['assets', u('assets')],
  ['settings', u('settings')],
  ['scene-training', u('home', 'training')],
  ['scene-portbusy', u('home', 'portbusy')],
  ['scene-firstrun', u('home', 'firstrun')],
  ['scene-empty', u('home', 'empty')],
];
let fontsReported = null;
for (const [name, url] of screens) {
  await load(url, name === 'scene-firstrun' ? 3000 : 900);
  if (!fontsReported) fontsReported = await fontCheck();
  const ov = await overflowCheck();
  const clip = await textClipCheck();
  ok('screen:' + name + ' 零溢出', ov.length === 0, ov.join(' | '));
  ok('screen:' + name + ' 无文本截断', clip.length === 0, clip.join(' | '));
  await shotWin(name);
}

// 权重标签页
await load(u('assets'));
await page.click('#assetSeg button[data-tab="weights"]');
await page.waitForTimeout(400);
await shotWin('weights');
ok('权重页零溢出', (await overflowCheck()).length === 0);

// ---------- 2. 字体加载 ----------
for (const [f, v] of Object.entries(fontsReported)) ok('字体加载:' + f, v.loaded, 'w1=' + v.w1 + ' w2=' + v.w2);

// ---------- 3. 交互测试 ----------
await load(u('home'));
await page.click('#btnLaunchConsole');
await page.waitForTimeout(3400);
ok('启动序列→运行中', (await page.textContent('#lmWord')).includes('运行中'), await page.textContent('#lmWord'));
ok('服务页芯片同步', (await page.textContent('#svcConsoleChipTxt')).includes('运行中'));
const logLines = await page.locator('#svcConsoleLines .ln').count();
ok('启动日志已追加', logLines >= 4, 'lines=' + logLines);

await page.click('.rn[data-nav="services"]');
await page.waitForTimeout(260);
await page.click('#svcConsoleStop');
await page.waitForTimeout(500);
ok('停止→未启动', (await page.textContent('#lmWord')).includes('未启动') || (await page.textContent('#lmWord')).includes('服务'), await page.textContent('#lmWord'));

// 导航
for (const s of ['services', 'env', 'assets', 'settings', 'home']) {
  await page.click('.rn[data-nav="' + s + '"]');
  await page.waitForTimeout(150);
  const onId = await page.evaluate(() => document.querySelector('.screen.on').id);
  ok('导航:' + s, onId === 'screen-' + s, onId);
}

// 场景切换
await page.click('#scenarioBtn'); await page.waitForTimeout(220);
await page.click('.pop-i[data-scene="training"]'); await page.waitForTimeout(420);
ok('场景:training 训练卡可见', await page.isVisible('#lmTraining'));
ok('场景:training 仪表同步', (await page.textContent('#vramTxt')).startsWith('11.2'));

await page.click('#scenarioBtn'); await page.waitForTimeout(260);
await page.click('.pop-i[data-scene="firstrun"]'); await page.waitForTimeout(600);
ok('场景:firstrun 向导打开', await page.isVisible('#wizard'));
await page.waitForFunction(() => { const b = document.querySelector('#wzNext1'); return !!b && !b.disabled; }, { timeout: 12000 }).catch(() => {});
const checks = await page.locator('#wzChecks .wcheck').count();
ok('向导检测行 ≥6', checks >= 6, 'rows=' + checks);
await page.click('#wzNext1'); await page.waitForTimeout(250);
await page.click('#wzNext2'); await page.waitForTimeout(250);
ok('向导到第 3 步', await page.isVisible('#wzP3'));
await page.keyboard.press('Escape'); await page.waitForTimeout(250);
ok('Esc 关闭向导', !(await page.isVisible('#wizard')));

// 模型下载模拟
await page.click('.rn[data-nav="assets"]'); await page.waitForTimeout(200);
await page.click('#assetSeg button[data-tab="weights"]'); await page.waitForTimeout(200);
await page.click('.mchip[data-model="yolov8l.pt"]');
await page.waitForTimeout(3200);
const isLocal = await page.evaluate(() => document.querySelector('.mchip[data-model="yolov8l.pt"]').classList.contains('local'));
ok('模型下载模拟完成', isLocal);

// 环境行展开
await page.click('.rn[data-nav="env"]'); await page.waitForTimeout(200);
await page.click('.erow[data-expand]');
await page.waitForTimeout(250);
ok('环境行展开', await page.isVisible('.erow[data-expand] + .edetail.on'));

// 总览页导航链接
await page.click('.rn[data-nav="home"]'); await page.waitForTimeout(200);
await page.click('.inst-note a'); await page.waitForTimeout(300);
ok('就绪仪表链接→环境', (await page.evaluate(() => document.querySelector('.screen.on').id)) === 'screen-env');

// ---------- 4. 汇总 ----------
const bad = results.filter(r => r.startsWith('FAIL'));
console.log(results.join('\n'));
console.log('\n===== RESULT: ' + (bad.length ? bad.length + ' FAIL' : 'ALL PASS') + ' =====');
console.log('\n===== CONSOLE/REQUEST ERRORS (' + errors.length + ') =====');
console.log(errors.slice(0, 20).join('\n') || '(none)');

await browser.close();
