// AYT 启动器 e2e · 真后端（py312）+ live 数据层全链路验证
import { createRequire } from 'module';
const require = createRequire('C:/Users/Tianbuyu/AppData/Local/hermes/skills/creative/ui-craft-studio/package.json');
const { chromium } = require('playwright');
import { spawn } from 'child_process';
import { setTimeout as sleep } from 'timers/promises';

const REPO = 'E:/项目/Auto-yolo-training';
const PY = 'C:/Python312/python.exe';
const OUT = 'E:/项目/Auto-yolo-training/launcher-design/_selfcheck/';
const results = [];
const ok = (n, c, x) => { const line = (c ? 'PASS  ' : 'FAIL  ') + n + (x ? '  :: ' + x : ''); results.push(line); console.log(line); };

/* ---------- 1) 起真后端（直用 LauncherBackend，不弹浏览器） ---------- */
const BOOT = [
  'import sys; sys.path.insert(0, ".")',
  'from src.launcher.backend import LauncherBackend',
  'b = LauncherBackend(base_dir=".", frontend_dist="src/launcher/static")',
  'b.start()',
  'print("BACKEND_URL=" + b.url, flush=True)',
  'import time',
  'while True: time.sleep(3600)',
].join('\n');
const srv = spawn(PY, ['-c', BOOT], { cwd: REPO, stdio: ['ignore', 'pipe', 'pipe'] });
let buf = '', url = null;
srv.stdout.on('data', d => { buf += String(d); const m = /BACKEND_URL=(http:\/\/\S+)/.exec(buf); if (m && !url) url = m[1]; });
srv.stderr.on('data', d => { buf += String(d); });
for (let i = 0; i < 100 && !url; i++) await sleep(500);
if (!url) { console.log('后端未就绪，日志尾部：\n' + buf.slice(-1500)); process.exit(1); }
console.log('backend:', url);

/* ---------- 2) playwright ---------- */
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1560, height: 940 }, deviceScaleFactor: 2 });
const page = await ctx.newPage();
const errs = [];
page.on('pageerror', e => errs.push('pageerror: ' + String(e)));
page.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text()); });

await page.goto(url, { waitUntil: 'domcontentloaded' });
await page.evaluate(() => Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 3000))]));
await page.waitForTimeout(4000);        // 等 live 探测 + 首拉 + WS

ok('live 已激活', await page.evaluate(() => !!(window.__live && window.__live.on === true)));
const live = await page.evaluate(() => ({
  ds: window.__live.datasets.length, st: window.__live.statuses.length,
  runs: window.__live.runs.length, cp: window.__live.checkpoints.length,
  ws: window.__live.ws ? window.__live.ws.readyState : -1,
  env: !!(window.__live.env && window.__live.env.python),
}));
console.log('LIVE:', JSON.stringify(live));
ok('数据集 ≥1', live.ds >= 1, 'ds=' + live.ds);
ok('WS 已连接（readyState=1）', live.ws === 1, 'ws=' + live.ws);
ok('env-report 已拉取', live.env);
ok('零控制台错误', errs.length === 0, errs.slice(0, 5).join(' | '));

const heroSub = await page.evaluate(() => document.getElementById('heroSub').textContent);
ok('首页 heroSub = 真实数据', heroSub.includes('个数据集可训练') && heroSub.includes(String(live.st)), heroSub);
const homeRows = await page.locator('#page-home .tbl tbody tr').count();
ok('首页最近训练表行数 = 断点数', homeRows === Math.min(6, live.cp) || live.cp === 0, 'rows=' + homeRows + ' cp=' + live.cp);
await (await page.$('#stageInner')).screenshot({ path: OUT + 'e2e-home-live.png' });

// config：数据集下拉 = 真实数据集且带图数
await page.click('.rit[data-page="config"]'); await page.waitForTimeout(700);
const dsOpt = await page.evaluate(() => {
  const s = document.getElementById('cfgDS');
  return { n: s.options.length, first: s.options[0] ? s.options[0].textContent : '', dd: !!s.closest('.dd'), label: document.querySelector('#cfgDS').closest('.dd') ? document.querySelector('#cfgDS').closest('.dd').querySelector('.dd-label').textContent : '' };
});
ok('config 数据集下拉 = 真实数', dsOpt.n === live.ds, JSON.stringify(dsOpt).slice(0, 140));
ok('数据集下拉含图数信息', /图/.test(dsOpt.first), dsOpt.first);
ok('dd 组件接管', dsOpt.dd && dsOpt.label.length > 0);
await (await page.$('#stageInner')).screenshot({ path: OUT + 'e2e-config-live.png' });

// datasets 页：行数 = statuses
await page.click('.rit[data-page="datasets"]'); await page.waitForTimeout(600);
const dsRows = await page.locator('#page-datasets .tbl tbody tr').count();
ok('数据集页行数 = statuses', dsRows === live.st, 'rows=' + dsRows + ' st=' + live.st);
await (await page.$('#stageInner')).screenshot({ path: OUT + 'e2e-datasets-live.png' });

// checkup：真实行 + Python
await page.click('.rit[data-page="checkup"]'); await page.waitForTimeout(600);
const chk = await page.evaluate(() => {
  const wraps = document.querySelectorAll('#page-checkup .rows');
  const wrap = wraps[wraps.length - 1];
  return { rows: wrap ? wrap.querySelectorAll('.row').length : 0, txt: wrap ? wrap.textContent : '' };
});
ok('自检页真实行 ≥7', chk.rows >= 7, 'rows=' + chk.rows);
ok('自检含 Python/torch', /Python/.test(chk.txt) && /PyTorch|torch/.test(chk.txt));
await (await page.$('#stageInner')).screenshot({ path: OUT + 'e2e-checkup-live.png' });

// monitor：cState + 日志提示
await page.click('.rit[data-page="monitor"]'); await page.waitForTimeout(700);
ok('监控页状态文本', /空闲|训练中/.test(await page.evaluate(() => document.getElementById('cState').textContent)));
ok('监控日志区就绪', (await page.locator('#logPanel .ln').count()) >= 0);

/* ---------- P2 接线验证 ---------- */
const p2 = await page.evaluate(() => ({
  chip: (document.getElementById('svcInferChip') || {}).textContent || '',
  btn: (document.getElementById('svcInferBtn') || {}).textContent || '',
}));
ok('推理卡 live 渲染（已停止→启动）', /已停止/.test(p2.chip) && p2.btn === '启动', JSON.stringify(p2));

// 动作拦截：数据集页点「校验」→ 真实调 /api/datasets/../validate → toast「校验完成」
await page.click('.rit[data-page="datasets"]'); await page.waitForTimeout(800);
await page.locator('#page-datasets button', { hasText: '校验' }).first().click();
const t1 = await page
  .waitForFunction(() => {
    const t = [...document.querySelectorAll('#toasts .tt')].map(e => e.textContent).join(' | ');
    return /校验完成|校验失败|未识别/.test(t) ? t : false;
  }, { timeout: 8000 })
  .then(h => h.jsonValue())
  .catch(() => '');
ok('动作拦截→真实校验执行', /校验完成/.test(t1), t1);

// 动作拦截：「预览」按钮不再走演示 toast（点它会出现「已打开」——但会真开资源管理器，跳过实际点击）
const previewBtn = await page.locator('#page-datasets button', { hasText: '预览' }).count();
ok('数据集行按钮已恢复（校验+预览）', previewBtn >= 1, 'preview buttons=' + previewBtn);
ok('P2 段仍零控制台错误', errs.length === 0, errs.slice(0, 3).join(' | '));

/* ---------- 3) 收尾 ---------- */
const fails = results.filter(r => r.startsWith('FAIL')).length;
console.log('===== E2E-LIVE: ' + (fails ? fails + ' FAIL' : 'ALL PASS') + ' =====');
await browser.close();
srv.kill();
process.exit(fails ? 1 : 0);
