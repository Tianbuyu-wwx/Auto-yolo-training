// v7 冒烟：新手/专家两态 + 参数弹窗全流程
import { createRequire } from 'module';
const require = createRequire('C:/Users/Tianbuyu/AppData/Local/hermes/skills/creative/ui-craft-studio/package.json');
const { chromium } = require('playwright');
const URL = 'file:///E:/%E9%A1%B9%E7%9B%AE/Auto-yolo-training/launcher-design/AYT-Launcher-v7.html?page=config#';
const OUT = 'E:/项目/Auto-yolo-training/launcher-design/_selfcheck/';
const results = [];
const ok = (n, c, x) => { results.push((c ? 'PASS  ' : 'FAIL  ') + n + (x ? '  :: ' + x : '')); };

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1560, height: 940 }, deviceScaleFactor: 2 });
const page = await ctx.newPage();
const errs = [];
page.on('pageerror', e => errs.push(String(e)));
page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
await page.goto(URL + '?t=' + Date.now(), { waitUntil: 'domcontentloaded' });
await page.evaluate(() => Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 3000))]));
await page.waitForTimeout(700);

// 1) 默认新手态
ok('新手 · 配方卡可见', await page.evaluate(() => getComputedStyle(document.getElementById('cfgRecipe')).display !== 'none'));
ok('新手 · 5 组卡隐藏', await page.evaluate(() => [...document.querySelectorAll('#page-config .cfg-right > .grp')].every(g => getComputedStyle(g).display === 'none')));
ok('新手 · 模式开关=新手', await page.evaluate(() => document.querySelector('#cfgModeTop button[data-cfgmode="basic"]').classList.contains('on')));
await (await page.$('#stageInner')).screenshot({ path: OUT + 'v7-config-novice.png' });

// 2) 打开「高级参数」全部弹窗
await page.click('#recipeOpen'); await page.waitForTimeout(450);
ok('弹窗 · 可见', await page.evaluate(() => !document.getElementById('pm').hidden && !document.getElementById('pmMask').hidden));
ok('弹窗 · 标题=全部', await page.evaluate(() => document.getElementById('pmTitle').textContent.includes('全部')));
ok('弹窗 · 5 组在弹窗内', await page.evaluate(() => ['basic','optim','reg','loss','aug'].every(k => document.getElementById('grp-' + k).closest('#pmBody'))));
ok('弹窗 · 小节标题 ×5', await page.locator('#pmBody .pm-sec').count() === 5);
ok('弹窗 · 字段可见（imgsz）', await page.evaluate(() => document.getElementById('f-imgsz').getBoundingClientRect().height > 0));
const fieldN = await page.locator('#pmBody input.inp, #pmBody select').count();
ok('弹窗 · 输入元素 ≥ 27', fieldN >= 27, 'n=' + fieldN);
await (await page.$('#stageInner')).screenshot({ path: OUT + 'v7-modal-all.png' });

// 3) 校验 + 取消恢复
await page.fill('#f-imgsz', '100'); await page.waitForTimeout(300);
ok('弹窗 · 校验错误显示', await page.evaluate(() => !document.getElementById('pmErr').hidden));
await page.click('#pmCancel'); await page.waitForTimeout(420);
ok('取消 · 弹窗关闭', await page.evaluate(() => document.getElementById('pm').hidden));
ok('取消 · 值恢复 640', await page.evaluate(() => document.getElementById('f-imgsz').value === '640'));
ok('取消 · 字段归位（#grp-basic 在 .grp 内）', await page.evaluate(() => {
  const el = document.getElementById('grp-basic');
  return el.closest('.grp') !== null && !el.closest('#pmBody');
}));
ok('取消 · 摘要同步恢复', await page.evaluate(() => document.getElementById('grp-d-basic').textContent.includes('640')));

// 4) 专家模式
await page.click('#cfgModeTop button[data-cfgmode="expert"]'); await page.waitForTimeout(420);
ok('专家 · 组卡 ×5 可见', await page.evaluate(() => [...document.querySelectorAll('#page-config .cfg-right > .grp')].every(g => getComputedStyle(g).display !== 'none')));
ok('专家 · 配方卡隐藏', await page.evaluate(() => getComputedStyle(document.getElementById('cfgRecipe')).display === 'none'));
ok('专家 · 设置页开关同步', await page.evaluate(() => document.querySelector('#cfgMode button[data-cfgmode="expert"]').classList.contains('on')));
await (await page.$('#stageInner')).screenshot({ path: OUT + 'v7-config-expert.png' });

// 5) 单组弹窗（basic）修改 → 完成 → 摘要动态更新
await page.click('.grp-toggle[data-grp="basic"]'); await page.waitForTimeout(420);
ok('单组弹窗 · 标题=训练规模', await page.evaluate(() => document.getElementById('pmTitle').textContent === '训练规模'));
ok('单组弹窗 · 无小节标题', await page.locator('#pmBody .pm-sec').count() === 0);
ok('单组弹窗 · optim 组仍在页面', await page.evaluate(() => !!document.getElementById('grp-optim').closest('.grp')));
await page.fill('#f-imgsz', '320'); await page.waitForTimeout(260);
await (await page.$('#stageInner')).screenshot({ path: OUT + 'v7-modal-basic.png' });
await page.click('#pmDone'); await page.waitForTimeout(420);
ok('完成 · 弹窗关闭', await page.evaluate(() => document.getElementById('pm').hidden));
ok('完成 · 值保留 320', await page.evaluate(() => document.getElementById('f-imgsz').value === '320'));
ok('完成 · 组摘要动态更新（含 320）', await page.evaluate(() => document.getElementById('grp-d-basic').textContent.includes('320')));
ok('完成 · 全局摘要含 320', await page.evaluate(() => document.getElementById('cfgSummary').textContent.includes('320')));

// 6) Esc 关闭 + 遮罩关闭
await page.click('.grp-toggle[data-grp="aug"]'); await page.waitForTimeout(380);
await page.keyboard.press('Escape'); await page.waitForTimeout(360);
ok('Esc · 弹窗关闭', await page.evaluate(() => document.getElementById('pm').hidden));
await page.click('.grp-toggle[data-grp="reg"]'); await page.waitForTimeout(380);
await page.click('#pmMask', { position: { x: 30, y: 30 } }); await page.waitForTimeout(360);
ok('遮罩点击 · 弹窗关闭', await page.evaluate(() => document.getElementById('pm').hidden));

// 7) 新手恢复 + 隐藏恢复
await page.click('#cfgModeTop button[data-cfgmode="basic"]'); await page.waitForTimeout(380);
ok('取消专家 · 配方卡复现', await page.evaluate(() => getComputedStyle(document.getElementById('cfgRecipe')).display !== 'none'));

ok('零控制台错误', errs.length === 0, errs.slice(0, 3).join(' | '));
console.log(results.join('\n'));
const fails = results.filter(r => r.startsWith('FAIL')).length;
console.log('===== SMOKE-V7: ' + (fails ? fails + ' FAIL' : 'ALL PASS') + ' =====');
await browser.close();
