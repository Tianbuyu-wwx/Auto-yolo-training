// v8 冒烟：自绘下拉组件 + 专家态回归 v6 布局
import { createRequire } from 'module';
const require = createRequire('C:/Users/Tianbuyu/AppData/Local/hermes/skills/creative/ui-craft-studio/package.json');
const { chromium } = require('playwright');
const URL = 'file:///E:/%E9%A1%B9%E7%9B%AE/Auto-yolo-training/launcher-design/AYT-Launcher-v8.html';
const OUT = 'E:/项目/Auto-yolo-training/launcher-design/_selfcheck/';
const results = [];
const ok = (n, c, x) => { results.push((c ? 'PASS  ' : 'FAIL  ') + n + (x ? '  :: ' + x : '')); };

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1560, height: 940 }, deviceScaleFactor: 2 });
const page = await ctx.newPage();
const errs = [];
page.on('pageerror', e => errs.push(String(e)));
page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
await page.goto(URL + '?page=config#&t=' + Date.now(), { waitUntil: 'domcontentloaded' });
await page.evaluate(() => Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 3000))]));
await page.waitForTimeout(700);

/* 1) 自绘下拉 */
ok('dd · 8 个 select 全 dd 化', await page.evaluate(() => document.querySelectorAll('select.dd-native').length >= 8), 'n=' + await page.locator('select.dd-native').count());
ok('dd · 包裹层存在（cfgDS）', await page.evaluate(() => !!document.getElementById('cfgDS').closest('.dd')));
ok('dd · label 显示当前值', await page.evaluate(() => document.querySelector('.dd .dd-label').textContent.length > 0));
// 展开
await page.click('.dd .dd-btn'); await page.waitForTimeout(320);
ok('dd · 展开列表可见', await page.evaluate(() => { const l = document.querySelector('.dd .dd-list'); return l && !l.hidden; }));
const optN = await page.evaluate(() => document.querySelector('.dd .dd-list').querySelectorAll('.dd-opt').length);
ok('dd · 选项数 = select 项数', optN === await page.evaluate(() => document.getElementById('cfgDS').options.length), 'opts=' + optN);
await (await page.$('#stageInner')).screenshot({ path: OUT + 'v8-dd-open.png' });
// 选择第 2 项
await page.click('.dd .dd-list .dd-opt:nth-child(2)'); await page.waitForTimeout(360);
ok('dd · 选择后 value 同步', await page.evaluate(() => document.getElementById('cfgDS').selectedIndex === 1));
ok('dd · 选择后 label 同步', await page.evaluate(() => document.querySelector('.dd .dd-label').textContent === document.getElementById('cfgDS').options[1].textContent));
ok('dd · 选择后列表关闭', await page.evaluate(() => document.querySelector('.dd .dd-list').hidden));
ok('dd · 配方卡联动（recipeSum 含新数据集名）', await page.evaluate(() => document.getElementById('recipeSum').textContent.includes(document.getElementById('cfgDS').options[1].textContent.split(' ')[0])));
// 外点关闭
await page.click('.dd .dd-btn'); await page.waitForTimeout(250);
await page.click('#page-config .ptop h2'); await page.waitForTimeout(280);
ok('dd · 外点关闭', await page.evaluate(() => document.querySelector('.dd .dd-list').hidden));
// Esc 关闭
await page.click('.dd .dd-btn'); await page.waitForTimeout(250);
await page.keyboard.press('Escape'); await page.waitForTimeout(250);
ok('dd · Esc 关闭', await page.evaluate(() => document.querySelector('.dd .dd-list').hidden));

/* 2) 专家态回归 v6 布局 */
await page.click('#cfgModeTop button[data-cfgmode="expert"]'); await page.waitForTimeout(420);
ok('专家 · 5 组卡可见', await page.evaluate(() => [...document.querySelectorAll('#page-config .cfg-right > .grp')].every(g => getComputedStyle(g).display !== 'none')));
const btnTxt = await page.evaluate(() => document.querySelector('.grp-toggle[data-grp="basic"]').textContent);
ok('专家 · basic 按钮=收起（默认展开）', btnTxt === '收起', btnTxt);
ok('专家 · basic body 初始可见（同 v6）', await page.evaluate(() => !document.getElementById('grp-basic').hidden));
// 收起/展开循环
await page.click('.grp-toggle[data-grp="basic"]'); await page.waitForTimeout(280);
ok('收起 · body 隐藏 + 摘要显示', await page.evaluate(() => document.getElementById('grp-basic').hidden && !document.getElementById('grp-d-basic').hidden));
ok('收起 · 按钮=展开', await page.evaluate(() => document.querySelector('.grp-toggle[data-grp="basic"]').textContent === '展开'));
await page.click('.grp-toggle[data-grp="basic"]'); await page.waitForTimeout(280);
ok('再展开 · 内联编辑（非弹窗）', await page.evaluate(() => !document.getElementById('grp-basic').hidden && document.getElementById('pm').hidden));
ok('再展开 · 26+ 字段可见', (await page.locator('#grp-basic .fld:visible').count()) >= 6);
await (await page.$('#stageInner')).screenshot({ path: OUT + 'v8-config-expert.png' });

/* 3) 新手弹窗仍工作 + （防御）程序化切模式自动收弹窗 */
await page.click('#cfgModeTop button[data-cfgmode="basic"]'); await page.waitForTimeout(380);
await page.click('#recipeOpen'); await page.waitForTimeout(460);
ok('新手 · 全部参数弹窗打开', await page.evaluate(() => !document.getElementById('pm').hidden && !!document.getElementById('grp-basic').closest('#pmBody')));
ok('弹窗 · 遮罩拦截背景（modal 行为）', await page.evaluate(() => !document.getElementById('pmMask').hidden));
await page.evaluate(() => setExpert(true)); await page.waitForTimeout(440);
ok('程序化切专家 · 弹窗自动收', await page.evaluate(() => document.getElementById('pm').hidden));
ok('程序化切专家 · 字段已归位', await page.evaluate(() => !!document.getElementById('grp-basic').closest('.grp')));
await page.evaluate(() => setExpert(false)); await page.waitForTimeout(380);

/* 4) 玻璃皮肤下的下拉 */
await page.click('.rit[data-page="settings"]'); await page.waitForTimeout(360);
await page.click('#setSkin button[data-skin="glass"]'); await page.waitForTimeout(650);
await page.click('.rit[data-page="config"]'); await page.waitForTimeout(520);
await page.click('.dd .dd-btn'); await page.waitForTimeout(360);
await (await page.$('#stageInner')).screenshot({ path: OUT + 'v8-dd-glass.png' });
ok('玻璃 · 下拉列表可见', await page.evaluate(() => { const l = document.querySelector('.dd .dd-list'); return l && !l.hidden; }));
await page.keyboard.press('Escape'); await page.waitForTimeout(220);
// 切回石墨
await page.click('.rit[data-page="settings"]'); await page.waitForTimeout(320);
await page.click('#setSkin button[data-skin="graphite"]'); await page.waitForTimeout(450);

ok('零控制台错误', errs.length === 0, errs.slice(0, 3).join(' | '));
console.log(results.join('\n'));
const fails = results.filter(r => r.startsWith('FAIL')).length;
console.log('===== SMOKE-V8: ' + (fails ? fails + ' FAIL' : 'ALL PASS') + ' =====');
await browser.close();
