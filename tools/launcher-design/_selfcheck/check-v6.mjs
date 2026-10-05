// AYT 启动器 v6 · 功能检查 + 状态截图（2x）—— v4 基线 + 液态玻璃主题 + 曲线引擎 v2
// 运行（任意目录免拷贝）：CHROME_PATH=… node check-v6.mjs
import { createRequire } from 'module';
const require = createRequire('C:/Users/Tianbuyu/AppData/Local/hermes/skills/creative/ui-craft-studio/package.json');
const { chromium } = require('playwright');
const URL = 'file:///E:/%E9%A1%B9%E7%9B%AE/Auto-yolo-training/tools/launcher-design/AYT-Launcher-v6.html';
const OUT = 'E:/项目/Auto-yolo-training/tools/launcher-design/_selfcheck/';

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
  ok('导航 = 9 项', await page.locator('.rit').count() === 9, 'n=' + await page.locator('.rit').count());
  ok('状态横幅 = 一切就绪', await page.evaluate(() => document.getElementById('heroTitle').textContent === '一切就绪'));
  ok('Jump in = 3 行', await page.locator('.jrow').count() === 3);
  ok('服务行 = 3', await page.locator('#page-home .rows .row').count() === 3);
  ok('最近训练 = 3 行', await page.locator('#page-home .tbl tbody tr').count() === 3);
  ok('主按钮 = 配置并启动训练', await page.evaluate(() => document.getElementById('btnRunLabel').textContent === '配置并启动训练'));

  // 导航逐页
  for (const [p, probe] of [
    ['datasets', '#page-datasets .tbl tbody tr'],
    ['config', '#grp-basic .f-grid .fld'],
    ['monitor', '#mEpoch'],
    ['results', '#page-results .stat-strip .stat'],
    ['registry', '#page-registry .tbl tbody tr'],
    ['queue', '#page-queue .empty-state b'],
    ['checkup', '#page-checkup .rows .row'],
    ['settings', '#set-gen .row'],
    ['home', '#page-home .status-hero']]) {
    await page.click(`.rit[data-page="${p}"]`);
    await page.waitForTimeout(320);
    const visible = await page.evaluate((sel) => {
      const el = document.querySelector(sel);
      return !!el && el.getBoundingClientRect().width > 0;
    }, probe);
    ok('页面 ' + p + ' 可见', visible);
  }

  // 数据集页
  await page.click('.rit[data-page="datasets"]'); await page.waitForTimeout(250);
  ok('数据集表 = 6 行', await page.locator('#page-datasets .tbl tbody tr').count() === 6, 'n=' + await page.locator('#page-datasets .tbl tbody tr').count());
  ok('缺标注横幅可见', await page.evaluate(() => document.querySelector('#page-datasets .warnbanner').textContent.includes('75')));

  // 训练配置：预设
  await page.click('.rit[data-page="config"]'); await page.waitForTimeout(250);
  ok('预设 = 3 个', await page.locator('#cfgPresets .pbtn').count() === 3);
  const inpN = await page.locator('#page-config input.inp').count();
  ok('参数输入 ≥ 27', inpN >= 27, 'n=' + inpN);
  await page.click('#cfgPresets .pbtn[data-preset="quick"]'); await page.waitForTimeout(300);
  ok('预设应用 · epochs=50', await page.evaluate(() => document.getElementById('f-epochs').value === '50'));
  ok('预设应用 · imgsz=416', await page.evaluate(() => document.getElementById('f-imgsz').value === '416'));
  ok('预设应用 · 摘要联动', await page.evaluate(() => document.getElementById('cfgSummary').textContent.includes('50 轮')));
  // 校验：32 倍数硬约束
  await page.fill('#f-imgsz', '100'); await page.waitForTimeout(250);
  ok('imgsz=100 · 报错可见', await page.evaluate(() => !document.getElementById('cfgErr').hidden));
  ok('imgsz=100 · 开始按钮禁用', await page.evaluate(() => document.getElementById('cfgRun').disabled));
  ok('imgsz=100 · 输入标红', await page.evaluate(() => document.getElementById('f-imgsz').classList.contains('invalid')));
  await page.fill('#f-imgsz', '320'); await page.waitForTimeout(250);
  ok('imgsz=320 · 恢复正常', await page.evaluate(() => document.getElementById('cfgErr').hidden && !document.getElementById('cfgRun').disabled));
  // 分组折叠
  ok('增强组默认收起', await page.evaluate(() => document.getElementById('grp-aug').hidden));
  await page.click('.grp-toggle[data-grp="aug"]'); await page.waitForTimeout(280);
  const augN = await page.locator('#grp-aug .fld:visible').count();
  ok('增强组展开 · 13 字段', augN === 13, 'n=' + augN);
  // 断点续训
  await page.click('#cfgResume'); await page.waitForTimeout(250);
  ok('断点续训 · 选择框出现', await page.evaluate(() => !document.getElementById('cfgResumeBox').hidden));

  // ⚡ 立即开始训练 → 场景切换 → 监控
  await page.click('#cfgRun'); await page.waitForTimeout(600);
  ok('开始训练 → 跳监控页', await page.evaluate(() => document.getElementById('page-monitor').classList.contains('on')));
  ok('监控 · 状态 = 训练中', await page.evaluate(() => document.getElementById('cState').textContent.includes('训练中')));
  ok('监控 · 进度 24.0%', await page.evaluate(() => document.getElementById('mpPct').textContent === '24.0%'));
  ok('监控 · Epoch 12/50', await page.evaluate(() => document.getElementById('mEpoch').textContent.replace(/\s/g, '') === '12/50'));
  ok('监控 · 曲线 2 图 3 线', await page.locator('.chart svg path[fill="none"]').count() === 3, 'n=' + await page.locator('.chart svg path[fill="none"]').count());
  ok('监控 · 停止按钮启用', await page.evaluate(() => !document.getElementById('btnKill').disabled));
  ok('日志 · 18 行', await page.locator('#logPanel .ln').count() === 18, 'n=' + await page.locator('#logPanel .ln').count());
  // 轮次定位
  await page.click('#logPanel .ln[data-ep="8"]'); await page.waitForTimeout(300);
  ok('点第 8 轮 · 芯片', await page.evaluate(() => !document.getElementById('epChip').hidden && document.getElementById('epChip').textContent.includes('8')));
  ok('点第 8 轮 · 曲线标记 ×2', await page.locator('.epmarker').count() === 2, 'n=' + await page.locator('.epmarker').count());
  ok('点第 8 轮 · 指标联动', await page.evaluate(() => document.getElementById('mLoss').textContent === '0.710'));
  ok('点第 8 轮 · 日志高亮 = 1', await page.locator('#logPanel .ln.sel').count() === 1);

  // 首页训练态联动
  await page.click('.rit[data-page="home"]'); await page.waitForTimeout(300);
  ok('首页 · 横幅 = 训练进行中', await page.evaluate(() => document.getElementById('heroTitle').textContent === '训练进行中'));
  ok('首页 · 训练卡 = 训练中', await page.evaluate(() => document.getElementById('svcTrainChip').textContent.includes('训练中')));
  ok('首页 · 进度条出现', await page.evaluate(() => !document.getElementById('tprog').hidden));
  ok('首页 · 主按钮 = 打开监控', await page.evaluate(() => document.getElementById('btnRunLabel').textContent === '打开监控'));

  // 停止训练
  await page.click('.rit[data-page="monitor"]'); await page.waitForTimeout(250);
  await page.click('#btnKill'); await page.waitForTimeout(400);
  ok('停止 → 空闲', await page.evaluate(() => document.getElementById('cState').textContent.includes('空闲')));
  ok('停止 → 曲线置空态', await page.evaluate(() => document.querySelector('#chartLoss').textContent.includes('训练开始后')));
  ok('停止 → 停止按钮禁用', await page.evaluate(() => document.getElementById('btnKill').disabled));

  // 推理服务开关（首页）
  await page.click('.rit[data-page="home"]'); await page.waitForTimeout(250);
  await page.click('#svcInferBtn'); await page.waitForTimeout(350);
  ok('推理启动 · chip=运行中', await page.evaluate(() => document.getElementById('svcInferChip').textContent.includes('运行中')));
  ok('推理启动 · 横幅=推理服务运行中', await page.evaluate(() => document.getElementById('heroTitle').textContent === '推理服务运行中'));
  await page.click('#svcInferBtn'); await page.waitForTimeout(350);
  ok('推理停止 · chip=已停止', await page.evaluate(() => document.getElementById('svcInferChip').textContent.includes('已停止')));

  // 场景：端口冲突
  await page.click('#scenarioBtn'); await page.waitForTimeout(200);
  await page.click('#scenarioPop .pop-i[data-scene="portbusy"]'); await page.waitForTimeout(500);
  ok('端口冲突 · 横幅', await page.evaluate(() => document.getElementById('homeBanner').textContent.includes('8000 被占用')));
  ok('端口冲突 · 跳首页', await page.evaluate(() => document.getElementById('page-home').classList.contains('on')));
  await page.click('#homeBanner button[data-act="p8001"]'); await page.waitForTimeout(400);
  ok('改用 8001 · 横幅消失', await page.evaluate(() => !document.getElementById('homeBanner').classList.contains('on')));

  // 场景：首次启动 / 空环境
  await page.click('#scenarioBtn'); await page.waitForTimeout(200);
  await page.click('#scenarioPop .pop-i[data-scene="firstrun"]'); await page.waitForTimeout(400);
  ok('首启 · 横幅', await page.evaluate(() => document.getElementById('homeBanner').textContent.includes('首次启动')));
  await page.click('#scenarioBtn'); await page.waitForTimeout(200);
  await page.click('#scenarioPop .pop-i[data-scene="empty"]'); await page.waitForTimeout(400);
  ok('空环境 · 横幅', await page.evaluate(() => document.getElementById('homeBanner').textContent.includes('还没有可训练数据集')));
  ok('空环境 · 主按钮=上传数据集', await page.evaluate(() => document.getElementById('btnRunLabel').textContent === '上传数据集'));
  await page.click('#scenarioBtn'); await page.waitForTimeout(200);
  await page.click('#scenarioPop .pop-i[data-scene="idle"]'); await page.waitForTimeout(300);

  // 结果 · 注册 · 队列 · 自检
  await page.click('.rit[data-page="results"]'); await page.waitForTimeout(250);
  ok('结果表 = 3 行', await page.locator('#page-results .tbl tbody tr').count() === 3);
  ok('统计条 = 4 格', await page.locator('#page-results .stat-strip .stat').count() === 4);
  await page.click('.rit[data-page="registry"]'); await page.waitForTimeout(250);
  ok('注册表 = 5 行', await page.locator('#page-registry .tbl tbody tr').count() === 5);
  await page.click('.rit[data-page="queue"]'); await page.waitForTimeout(250);
  ok('队列空态 · CTA 在场', await page.evaluate(() => document.querySelector('#page-queue .empty-state .btn') !== null));
  ok('队列说明 = 3 行', await page.locator('#page-queue .rows .row').count() === 3);
  await page.click('.rit[data-page="checkup"]'); await page.waitForTimeout(250);
  const chkN = await page.locator('#page-checkup .row').count();
  ok('自检行 = 14', chkN === 14, 'n=' + chkN);

  // 设置：专家模式 + 浅色 + 青瓷
  await page.click('.rit[data-page="settings"]'); await page.waitForTimeout(250);
  ok('新手 · 专家行隐藏', await page.locator('#page-settings .blk.expert .row:visible').count() === 0);
  await page.click('#cfgMode button[data-cfgmode="expert"]'); await page.waitForTimeout(400);
  const expN = await page.locator('#page-settings .blk.expert .row:visible').count();
  ok('专家 · 高级行显示 9', expN === 9, 'n=' + expN);
  await page.click('#setMode button[data-mode="light"]'); await page.waitForTimeout(400);
  ok('切浅色', await page.evaluate(() => document.documentElement.dataset.mode === 'light'));
  await page.click('#setAcc button[data-accent="celadon"]'); await page.waitForTimeout(300);
  ok('切青瓷', await page.evaluate(() => document.documentElement.dataset.accent === 'celadon'));

  // 逐页溢出检查
  for (const p of ['home', 'datasets', 'config', 'monitor', 'results', 'registry', 'queue', 'checkup', 'settings']) {
    await page.click(`.rit[data-page="${p}"]`); await page.waitForTimeout(350);
    const overflow = await page.evaluate(() => {
      const win = document.getElementById('win').getBoundingClientRect();
      let bad = 0;
      document.querySelectorAll('.page.on *').forEach(e => {
        const r = e.getBoundingClientRect();
        if (!r.width) return;
        if (e.tagName === 'svg' || e.ownerSVGElement) return;            // 跳过 SVG 装饰几何
        if (r.right > win.right + 1 || r.left < win.left - 1) { bad++; return; }
        const inScroll = e.closest('.pscroll') || e.closest('.log') || e.closest('.home-left');
        if (!inScroll && r.bottom > win.bottom + 1) bad++;
      });
      return bad;
    });
    ok('页面 ' + p + ' 零溢出', overflow === 0, 'overflow=' + overflow);
  }
  // ---------- v6 断言：续训互斥 / 曲线 v2 / 皮肤与氛围 ----------
  await page.click('.rit[data-page="config"]'); await page.waitForTimeout(400);
  /* 归一化：v4 流程曾开启续训，先确保为关（互斥切换是 toggle） */
  if (!(await page.evaluate(() => document.getElementById('cfgResumeBox').hidden))){
    await page.click('#cfgResume'); await page.waitForTimeout(420);
  }
  const rmB = await page.evaluate(() => { const sc = document.querySelector('#page-config .pscroll'); return sc.scrollHeight - sc.clientHeight; });
  await page.click('#cfgResume'); await page.waitForTimeout(440);
  ok('v6 续训 · 选择框显示', await page.evaluate(() => !document.getElementById('cfgResumeBox').hidden));
  ok('v6 续训 · 摘要隐藏（互斥）', await page.evaluate(() => document.getElementById('cfgSummary').hidden));
  const rmA = await page.evaluate(() => { const sc = document.querySelector('#page-config .pscroll'); return sc.scrollHeight - sc.clientHeight; });
  ok('v6 续训 · 零高度增长', rmB === rmA, rmB + ' → ' + rmA);
  await page.click('#cfgResume'); await page.waitForTimeout(400);
  ok('v6 续训关闭 · 摘要恢复', await page.evaluate(() => !document.getElementById('cfgSummary').hidden && document.getElementById('cfgResumeBox').hidden));

  await page.click('.rit[data-page="monitor"]'); await page.waitForTimeout(300);
  await page.click('#scenarioBtn'); await page.waitForTimeout(160);
  await page.click('#scenarioPop .pop-i[data-scene="training"]'); await page.waitForTimeout(680);
  ok('v6 曲线 · 平滑路径（C 命令）', await page.evaluate(() => {
    const p = document.querySelector('#chartLoss svg path[fill="none"]');
    return !!p && (p.getAttribute('d') || '').includes('C');
  }));
  ok('v6 曲线 · 面积渐变 ×2', await page.locator('#chartLoss svg path[fill^="url("], #chartMap svg path[fill^="url("]').count() >= 2);
  ok('v6 曲线 · 图例 mAP@50/95', await page.evaluate(() => { const t = document.querySelector('#chartMap svg').textContent; return t.includes('mAP@50') && t.includes('mAP@95'); }));
  ok('v6 曲线 · X 轴 E 标签 ×3', await page.evaluate(() => [...document.querySelectorAll('#chartMap svg text')].filter(t => /^E\d/.test(t.textContent)).length >= 3));
  ok('v6 曲线 · live-dot 末点', await page.locator('#chartMap svg .live-dot').count() === 1);
  ok('v6 曲线 · hover 引导元素', await page.locator('#chartMap svg .hover-guide').count() >= 4);

  await page.click('.rit[data-page="settings"]'); await page.waitForTimeout(360);
  ok('v6 皮肤 · 默认石墨（无 data-skin）', await page.evaluate(() => !document.documentElement.dataset.skin));
  ok('v6 氛围 · 默认隐藏', await page.evaluate(() => getComputedStyle(document.getElementById('atmo')).display === 'none'));
  await page.click('#setSkin button[data-skin="glass"]'); await page.waitForTimeout(680);
  ok('v6 皮肤 · 切玻璃', await page.evaluate(() => document.documentElement.dataset.skin === 'glass'));
  ok('v6 氛围 · 玻璃下显示', await page.evaluate(() => getComputedStyle(document.getElementById('atmo')).display !== 'none'));
  ok('v6 氛围 · 引擎运行', await page.evaluate(() => !document.getElementById('atmo').classList.contains('off')));
  await page.click('#setSkin button[data-skin="graphite"]'); await page.waitForTimeout(480);
  ok('v6 皮肤 · 切回石墨', await page.evaluate(() => !document.documentElement.dataset.skin));
  ok('v6 氛围 · 切回后隐藏', await page.evaluate(() => getComputedStyle(document.getElementById('atmo')).display === 'none'));

  ok('无控制台错误', errs.length === 0, errs.slice(0, 2).join(' | '));
  await page.close();
}
} catch (e) { results.push('FAIL  功能流程异常 :: ' + String(e.message || e).split('\n')[0]); }

console.log(results.join('\n'));
const fails = results.filter(r => r.startsWith('FAIL')).length;
console.log('===== RESULT: ' + (fails ? fails + ' FAIL' : 'ALL PASS') + ' =====');

// ---------- 截图 ----------
async function shot(name, suffix, setup, mode, skin){
  const ctx = await browser.newContext({ viewport: { width: 1560, height: 940 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  if (mode || skin) await page.addInitScript(([m, sk]) => {
    if (m) localStorage.setItem('ayt.theme', JSON.stringify({ mode: m, accent: 'brass' }));
    if (sk === 'glass') localStorage.setItem('ayt.skin', 'glass');
  }, [mode || null, skin || null]);
  await page.goto(URL + '?t=' + Date.now() + (suffix || '').replace(/^\?/, '&'), { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 3000))]));
  await page.waitForTimeout(650);
  if (setup) await setup(page);
  await page.waitForTimeout(500);
  await (await page.$('#stageInner')).screenshot({ path: OUT + name + '.png' });
  await ctx.close(); console.log('shot ->', name);
}

await shot('v4-home', '');
await shot('v4-home-light', '', null, 'light');
await shot('v4-datasets', '?page=datasets#');
await shot('v4-config', '?page=config#');
await shot('v4-config-aug', '?page=config#', async (p) => {
  await p.click('.grp-toggle[data-grp="aug"]'); await p.waitForTimeout(300);
  await p.evaluate(() => { document.querySelector('#page-config .pscroll').scrollTop = 430; }); await p.waitForTimeout(350);
});
await shot('v4-monitor', '?page=monitor&scene=training#');
await shot('v4-monitor-light', '?page=monitor&scene=training#', null, 'light');
await shot('v4-results', '?page=results#');
await shot('v4-registry', '?page=registry#');
await shot('v4-queue', '?page=queue#');
await shot('v4-checkup', '?page=checkup#');
await shot('v4-settings', '?page=settings#');
await shot('v4-home-portbusy', '', async (p) => {
  await p.click('#scenarioBtn'); await p.waitForTimeout(200);
  await p.click('#scenarioPop .pop-i[data-scene="portbusy"]'); await p.waitForTimeout(400);
  await p.click('.rit[data-page="home"]'); await p.waitForTimeout(500);
});
await shot('v4-home-training', '', async (p) => {
  await p.click('#scenarioBtn'); await p.waitForTimeout(200);
  await p.click('#scenarioPop .pop-i[data-scene="training"]'); await p.waitForTimeout(400);
  await p.click('.rit[data-page="home"]'); await p.waitForTimeout(500);
});

/* ---------- v6 增量截图 ---------- */
await shot('v6-config-resume', '?page=config#', async (p) => {
  await p.click('#cfgResume'); await p.waitForTimeout(500);
});
await shot('v6-monitor-curve', '?page=monitor&scene=training#', async (p) => {
  await p.hover('#chartMap svg', { position: { x: 320, y: 58 } }); await p.waitForTimeout(260);
});
await shot('v6-home-glass', '', async (p) => {
  await p.mouse.move(420, 320); await p.waitForTimeout(120);
  await p.mouse.move(860, 460); await p.waitForTimeout(360);
}, null, 'glass');
await shot('v6-monitor-glass', '?page=monitor&scene=training#', null, null, 'glass');
await shot('v6-settings-glass', '?page=settings#', null, null, 'glass');

console.log('ALL SHOTS DONE');
await browser.close();
process.exit(fails ? 1 : 0);
