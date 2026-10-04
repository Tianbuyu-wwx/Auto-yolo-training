// AYT 启动器 v2 · 功能检查 + 状态截图（2x）—— 26 项功能断言 + 11 张状态图
// 运行（需 ui-craft-studio skill 目录的 node_modules / playwright）：
//   CHROME_PATH="…/msedge.exe" node check-v2.mjs
import { chromium } from 'playwright';
const URL = 'file:///E:/%E9%A1%B9%E7%9B%AE/Auto-yolo-training/launcher-design/AYT-Launcher-v2.html';
const OUT = 'E:/项目/Auto-yolo-training/launcher-design/_selfcheck/';

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, headless: true });
const results = [];
const ok = (n, c, x) => results.push((c ? 'PASS  ' : 'FAIL  ') + n + (x ? '  :: ' + x : ''));

// ---------- 功能 ----------
try {
{
  const page = await browser.newPage({ viewport: { width: 1560, height: 940 } });
  const errs = [];
  page.on('pageerror', e => errs.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  await page.goto(URL + '?t=' + Date.now(), { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 3000))]));
  await page.waitForTimeout(600);

  ok('初始 = idle', await page.evaluate(() => document.getElementById('primaryLabel').textContent === '启动控制台'));
  ok('状态行 = 就绪', await page.evaluate(() => document.getElementById('statusText').textContent.includes('环境就绪')));
  ok('底栏版本', await page.evaluate(() => document.querySelector('.fbar .mono').textContent.includes('9e05411')));

  // 启动序列
  await page.click('#btnPrimary');
  await page.waitForTimeout(500);
  ok('接管层已开', await page.isVisible('#takeover'));
  await page.waitForSelector('#tkSteps .tk-step.in', { timeout: 3000 }).catch(() => {});
  const stepCount = await page.locator('#tkSteps .tk-step.in').count();
  ok('启动步骤开始出现', stepCount >= 1, 'n=' + stepCount);
  await page.waitForFunction(() => !document.getElementById('takeover').classList.contains('on'), { timeout: 9000 }).catch(() => {});
  await page.waitForTimeout(400);
  ok('启动完成 → running', await page.evaluate(() => document.getElementById('primaryLabel').textContent === '打开控制台'));
  ok('停止按钮出现', await page.evaluate(() => !document.getElementById('btnStop').hidden));
  ok('底栏 :8080', await page.evaluate(() => document.getElementById('fbRight').textContent.includes(':8080')));
  ok('Toast 出现', await page.locator('#toasts .toast').count() >= 1);

  // 停止
  await page.click('#btnStop');
  await page.waitForTimeout(400);
  ok('停止 → idle', await page.evaluate(() => document.getElementById('primaryLabel').textContent === '启动控制台'));

  // 推理服务
  await page.click('#btnServe');
  await page.waitForFunction(() => !document.getElementById('takeover').classList.contains('on'), { timeout: 9000 }).catch(() => {});
  await page.waitForTimeout(300);
  ok('推理启动完成', await page.evaluate(() => document.getElementById('btnServe').textContent === '停止推理'));
  ok('底栏 :8000', await page.evaluate(() => document.getElementById('fbRight').textContent.includes(':8000')));
  await page.click('#btnServe'); // 停回
  await page.waitForTimeout(200);

  // 设置弹层
  await page.click('#setBtn');
  await page.waitForTimeout(300);
  ok('设置弹层打开', await page.isVisible('#setPop'));
  ok('设置行数 =4', await page.locator('#setPop .sline').count() === 4);
  await page.locator('#setPop .switch').first().click();
  ok('开关可切', await page.evaluate(() => !document.querySelector('#setPop .switch').classList.contains('on')));
  await page.keyboard.press('Escape');
  await page.waitForTimeout(200);
  ok('Esc 关设置', await page.evaluate(() => !document.getElementById('setPop').classList.contains('on')));

  // 主题
  await page.click('#themeBtn'); await page.waitForTimeout(250);
  ok('外观弹层打开', await page.isVisible('#themePop'));
  await page.click('#tpMode button[data-mode="light"]'); await page.waitForTimeout(450);
  ok('切浅色', await page.evaluate(() => document.documentElement.dataset.mode === 'light'));
  await page.click('#tpAcc button[data-accent="celadon"]'); await page.waitForTimeout(450);
  ok('切青瓷', await page.evaluate(() => document.documentElement.dataset.accent === 'celadon'));
  await page.keyboard.press('Escape'); await page.waitForTimeout(150);
  // 还原
  await page.evaluate(() => localStorage.removeItem('ayt.theme'));
  await page.reload({ waitUntil: 'domcontentloaded' }); await page.waitForTimeout(700);

  // 场景切换（含各态关键 DOM + 溢出检查）
  const scenes = ['running', 'training', 'portbusy', 'firstrun', 'empty', 'idle'];
  for (const sc of scenes){
    await page.click('#scenarioBtn'); await page.waitForTimeout(160);
    await page.click(`#scenarioPop .pop-i[data-scene="${sc}"]`);
    await page.waitForTimeout(900);
    const overflow = await page.evaluate(() => {
      const win = document.getElementById('win').getBoundingClientRect();
      let bad = 0;
      document.querySelectorAll('#win *').forEach(e => {
        const r = e.getBoundingClientRect();
        if (r.width && (r.right > win.right + 1 || r.bottom > win.bottom + 1 || r.left < win.left - 1)) {
          const cs = getComputedStyle(e);
          if (cs.position !== 'fixed' && e.id !== 'stageInner') bad++;
        }
      });
      return bad;
    });
    ok('场景 ' + sc + ' 零溢出', overflow === 0, 'overflow=' + overflow);
  }
  ok('无控制台错误', errs.length === 0, errs.slice(0, 2).join(' | '));
  await page.close();
}
} catch (e) { results.push('FAIL  功能流程异常 :: ' + String(e.message || e).split('\n')[0]); }

console.log(results.join('\n'));
const fails = results.filter(r => r.startsWith('FAIL')).length;
console.log('===== RESULT: ' + (fails ? fails + ' FAIL' : 'ALL PASS') + ' =====');

// ---------- 截图（2x，各状态） ----------
async function shot(name, suffix, setup){
  const ctx = await browser.newContext({ viewport: { width: 1560, height: 940 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  await page.goto(URL + '?t=' + Date.now() + (suffix || '').replace(/^\?/, '&'), { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 3000))]));
  await page.waitForTimeout(700);
  if (setup) await setup(page);
  await page.waitForTimeout(600);
  await (await page.$('#stageInner')).screenshot({ path: OUT + name + '.png' });
  await ctx.close(); console.log('shot ->', name);
}

await shot('v2-idle', '');
await shot('v2-idle-light', '', async (p) => { await p.evaluate(() => localStorage.setItem('ayt.theme', JSON.stringify({ mode: 'light', accent: 'brass' }))); await p.reload({ waitUntil: 'domcontentloaded' }); await p.waitForTimeout(800); });
await shot('v2-launching', '', async (p) => { await p.click('#btnPrimary'); await p.waitForTimeout(1450); });
await shot('v2-running', '?scene=running#');
await shot('v2-training', '?scene=training#');
await shot('v2-portbusy', '?scene=portbusy#');
await shot('v2-firstrun', '?scene=firstrun#', async (p) => { await new Promise(r => setTimeout(r, 2200)); });
await shot('v2-empty', '?scene=empty#');
await shot('v2-pop-theme', '', async (p) => { await p.click('#themeBtn'); });
await shot('v2-pop-set', '', async (p) => { await p.click('#setBtn'); });
await shot('v2-pop-scene', '', async (p) => { await p.click('#scenarioBtn'); });

console.log('ALL SHOTS DONE');
await browser.close();
process.exit(fails ? 1 : 0);
