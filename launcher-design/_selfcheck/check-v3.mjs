// AYT 启动器 v3 · 功能检查 + 状态截图（2x）—— 绘世式工作台
// 运行（需 ui-craft-studio skill 目录的 playwright）：CHROME_PATH=… node check-v3.mjs
import { chromium } from 'playwright';
const URL = 'file:///E:/%E9%A1%B9%E7%9B%AE/Auto-yolo-training/launcher-design/AYT-Launcher-v3.html';
const OUT = 'E:/项目/Auto-yolo-training/launcher-design/_selfcheck/';

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, headless: true });
const results = [];
const ok = (n, c, x) => results.push((c ? 'PASS  ' : 'FAIL  ') + n + (x ? '  :: ' + x : ''));

try {
{
  const page = await browser.newPage({ viewport: { width: 1560, height: 940 } });
  const errs = [];
  page.on('pageerror', e => errs.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  await page.goto(URL + '?t=' + Date.now(), { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 3000))]));
  await page.waitForTimeout(500);

  // 首页初始
  ok('初始 = 首页', await page.evaluate(() => document.getElementById('page-home').classList.contains('on')));
  ok('导航高亮 = 一键启动', await page.evaluate(() => document.querySelector('.rit[data-page="home"]').classList.contains('on')));
  ok('快捷卡 = 6', await page.locator('.qcard').count() === 6);
  ok('主按钮 = 一键启动', await page.evaluate(() => document.getElementById('btnRunLabel').textContent === '一键启动'));
  ok('状态行 = 端口空闲', await page.evaluate(() => document.getElementById('chipPort').textContent.includes('空闲')));

  // 导航逐页
  for (const [p, probe] of [
    ['advanced', '#adv-train .row'], ['faq', '#faqList .frow'],
    ['models', '#mod-ds .dcard'], ['console', '#logPanel .ln'], ['settings', '#set-gen .row'], ['home', '#page-home .hero']]) {
    await page.click(`.rit[data-page="${p}"]`);
    await page.waitForTimeout(320);
    const visible = await page.evaluate((sel) => {
      const el = document.querySelector(sel);
      return !!el && el.getBoundingClientRect().width > 0;
    }, probe);
    ok('页面 ' + p + ' 可见', visible);
  }

  // 一键启动 → 控制台
  await page.click('#btnRun');
  await page.waitForTimeout(600);
  ok('启动 → 跳到控制台', await page.evaluate(() => document.getElementById('page-console').classList.contains('on')));
  ok('日志流式输出中', await page.locator('#logPanel .ln').count() >= 1, 'n=' + await page.locator('#logPanel .ln').count());
  await page.waitForFunction(() => document.getElementById('cState').textContent.includes('运行中'), { timeout: 9000 }).catch(() => {});
  const logN = await page.locator('#logPanel .ln').count();
  ok('启动完成 · 日志完整', logN >= 9, 'lines=' + logN);
  ok('控制台状态 = 运行中', await page.evaluate(() => document.getElementById('cState').textContent.includes('运行中')));
  ok('终止按钮已启用', await page.evaluate(() => !document.getElementById('btnKill').disabled));

  // 回首页看联动
  await page.click('.rit[data-page="home"]');
  await page.waitForTimeout(300);
  ok('首页按钮联动 → 打开控制台', await page.evaluate(() => document.getElementById('btnRunLabel').textContent === '打开控制台'));
  ok('首页端口 chip = :8080', await page.evaluate(() => document.getElementById('chipPort').textContent.includes(':8080')));

  // 终止进程
  await page.click('.rit[data-page="console"]');
  await page.waitForTimeout(250);
  await page.click('#btnKill');
  await page.waitForTimeout(400);
  ok('终止 → 未运行', await page.evaluate(() => document.getElementById('cState').textContent.includes('未运行')));

  // 场景：训练中
  await page.click('#scenarioBtn'); await page.waitForTimeout(200);
  await page.click('#scenarioPop .pop-i[data-scene="training"]');
  await page.waitForTimeout(500);
  ok('训练场景 · 控制台 = 训练中', await page.evaluate(() => document.getElementById('cState').textContent.includes('训练中')));
  await page.click('.rit[data-page="home"]'); await page.waitForTimeout(250);
  ok('训练场景 · 首页进度条出现', await page.evaluate(() => !document.getElementById('tprog').hidden));
  ok('训练场景 · 主按钮 = 打开监控', await page.evaluate(() => document.getElementById('btnRunLabel').textContent === '打开监控'));

  // 场景：端口冲突
  await page.click('#scenarioBtn'); await page.waitForTimeout(200);
  await page.click('#scenarioPop .pop-i[data-scene="portbusy"]');
  await page.waitForTimeout(500);
  ok('端口冲突 · 首页横幅', await page.evaluate(() => document.getElementById('homeBanner').textContent.includes('8080 被占用')));
  ok('端口冲突 · 跳到控制台', await page.evaluate(() => document.getElementById('page-console').classList.contains('on')));
  ok('端口冲突 · 按钮 = 改用 8081', await page.evaluate(() => document.getElementById('btnRun2').textContent.includes('8081')));

  // 场景：首次启动
  await page.click('#scenarioBtn'); await page.waitForTimeout(200);
  await page.click('#scenarioPop .pop-i[data-scene="firstrun"]');
  await page.waitForTimeout(500);
  ok('首启场景 · 回首页横幅', await page.evaluate(() => document.getElementById('homeBanner').textContent.includes('首次启动')));

  // 场景：回就绪
  await page.click('#scenarioBtn'); await page.waitForTimeout(200);
  await page.click('#scenarioPop .pop-i[data-scene="idle"]');
  await page.waitForTimeout(300);

  // 模型管理三标签
  await page.click('.rit[data-page="models"]'); await page.waitForTimeout(250);
  ok('数据集卡 = 6', await page.locator('#mod-ds .dcard').count() === 6);
  await page.click('#page-models .tab[data-tab="wt"]');
  await page.waitForTimeout(250);
  ok('权重表 = 7 行', await page.locator('#mod-wt .tbl tbody tr').count() === 7);
  await page.click('#page-models .tab[data-tab="run"]');
  await page.waitForTimeout(250);
  ok('训练记录 = 4 行', await page.locator('#mod-run .rrow').count() === 4);

  // 高级选项三标签
  await page.click('.rit[data-page="advanced"]'); await page.waitForTimeout(250);
  ok('训练设置行 ≥ 10', await page.locator('#adv-train .row').count() >= 10);
  await page.click('#page-advanced .tab[data-tab="env"]'); await page.waitForTimeout(250);
  ok('环境维护可见行 ≥ 4', await page.locator('#adv-env .row:visible').count() >= 4);
  await page.click('#page-advanced .tab[data-tab="boot"]'); await page.waitForTimeout(250);
  ok('启动选项含端口输入', await page.locator('#adv-boot input.inp').count() === 2);

  // 设置：专家模式
  await page.click('.rit[data-page="settings"]'); await page.waitForTimeout(250);
  const expertHidden = await page.locator('#page-settings .blk.expert .row:visible').count();
  ok('新手模式 · 专家行隐藏', expertHidden === 0, 'visible=' + expertHidden);
  ok('新手模式 · 提示可见', await page.isVisible('#expertNote'));
  await page.click('#cfgMode button[data-cfgmode="expert"]');
  await page.waitForTimeout(400);
  const expertShown = await page.locator('#page-settings .blk.expert .row:visible').count();
  ok('专家模式 · 高级行显示 9', expertShown === 9, 'visible=' + expertShown);
  ok('专家模式 · 提示隐藏', await page.evaluate(() => !document.getElementById('expertNote').offsetParent));

  // 设置主题（设置页控件）
  await page.click('#setMode button[data-mode="light"]');
  await page.waitForTimeout(400);
  ok('设置页切浅色', await page.evaluate(() => document.documentElement.dataset.mode === 'light'));
  await page.click('#setAcc button[data-accent="celadon"]');
  await page.waitForTimeout(400);
  ok('设置页切青瓷', await page.evaluate(() => document.documentElement.dataset.accent === 'celadon'));

  // 标题栏外观弹层
  await page.click('#themeBtn'); await page.waitForTimeout(250);
  ok('外观弹层可开', await page.isVisible('#themePop'));
  await page.keyboard.press('Escape'); await page.waitForTimeout(200);

  // 疑难解答扫描
  await page.click('.rit[data-page="faq"]'); await page.waitForTimeout(250);
  await page.click('#btnScan'); await page.waitForTimeout(600);
  ok('扫描触发 toast', await page.locator('#toasts .toast').count() >= 1);

  // 逐页溢出检查
  for (const p of ['home', 'advanced', 'faq', 'models', 'console', 'settings']) {
    await page.click(`.rit[data-page="${p}"]`); await page.waitForTimeout(350);
    const overflow = await page.evaluate(() => {
      const win = document.getElementById('win').getBoundingClientRect();
      let bad = 0;
      document.querySelectorAll('.page.on *').forEach(e => {
        const r = e.getBoundingClientRect();
        if (!r.width) return;
        if (e.tagName === 'svg' || e.ownerSVGElement) return;            // 跳过 SVG 装饰几何（被裁切，非布局问题）
        if (r.right > win.right + 1 || r.left < win.left - 1) { bad++; return; }  // 水平溢出永远算问题
        const inScroll = e.closest('.pscroll') || e.closest('.log');
        if (!inScroll && r.bottom > win.bottom + 1) bad++;               // 纵向：可滚动区内豁免
      });
      return bad;
    });
    ok('页面 ' + p + ' 零溢出', overflow === 0, 'overflow=' + overflow);
  }
  ok('无控制台错误', errs.length === 0, errs.slice(0, 2).join(' | '));
  await page.close();
}
} catch (e) { results.push('FAIL  功能流程异常 :: ' + String(e.message || e).split('\n')[0]); }

console.log(results.join('\n'));
const fails = results.filter(r => r.startsWith('FAIL')).length;
console.log('===== RESULT: ' + (fails ? fails + ' FAIL' : 'ALL PASS') + ' =====');

// ---------- 截图 ----------
async function shot(name, suffix, setup, mode){
  const ctx = await browser.newContext({ viewport: { width: 1560, height: 940 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  if (mode) await page.addInitScript((m) => localStorage.setItem('ayt.theme', JSON.stringify({ mode: m, accent: 'brass' })), mode);
  await page.goto(URL + '?t=' + Date.now() + (suffix || '').replace(/^\?/, '&'), { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 3000))]));
  await page.waitForTimeout(650);
  if (setup) await setup(page);
  await page.waitForTimeout(500);
  await (await page.$('#stageInner')).screenshot({ path: OUT + name + '.png' });
  await ctx.close(); console.log('shot ->', name);
}

await shot('v3-home', '');
await shot('v3-home-light', '', null, 'light');
await shot('v3-console', '?page=console&scene=running#');
await shot('v3-adv-train', '?page=advanced#');
await shot('v3-adv-env', '?page=advanced&adv=env#');
await shot('v3-faq', '?page=faq#');
await shot('v3-models-ds', '?page=models#');
await shot('v3-models-wt', '?page=models&mod=wt#');
await shot('v3-models-run', '?page=models&mod=run#');
await shot('v3-settings', '?page=settings#');
await shot('v3-settings-expert', '?page=settings&expert=1#');
await shot('v3-home-portbusy', '', async (p) => {
  await p.click('#scenarioBtn'); await p.waitForTimeout(200);
  await p.click('#scenarioPop .pop-i[data-scene="portbusy"]'); await p.waitForTimeout(400);
  await p.click('.rit[data-page="home"]'); await p.waitForTimeout(500);
});
await shot('v3-pop-theme', '', async (p) => { await p.click('#themeBtn'); });

console.log('ALL SHOTS DONE');
await browser.close();
process.exit(fails ? 1 : 0);
