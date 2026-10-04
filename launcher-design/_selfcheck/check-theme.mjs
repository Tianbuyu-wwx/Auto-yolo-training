// 主题系统功能测试：模式切换 / 强调色 / 自定义 / 持久化 / 跟随系统 / 弹层互斥 / Esc
// 运行：复制到 ui-craft-studio skill 目录后：
//   cd <skill目录> && CHROME_PATH="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" node check-theme.mjs
import { chromium } from 'playwright';
const URL = 'file:///E:/%E9%A1%B9%E7%9B%AE/Auto-yolo-training/launcher-design/AYT-Launcher-v1.html';

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, headless: true });
const page = await browser.newPage({ viewport: { width: 1560, height: 940 } });
const results = [];
const ok = (name, cond, extra) => results.push((cond ? 'PASS  ' : 'FAIL  ') + name + (extra ? '  :: ' + extra : ''));

await page.goto(URL + '?t=' + Date.now(), { waitUntil: 'domcontentloaded' });
await page.evaluate(() => Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 3000))]));
await page.waitForTimeout(700);

// 1) 默认深色
ok('默认 data-mode=dark', await page.evaluate(() => document.documentElement.dataset.mode === 'dark'));

// 2) 打开弹层
await page.click('#themeBtn'); await page.waitForTimeout(240);
ok('外观弹层打开', await page.isVisible('#themePop'));
ok('模式按钮高亮同步(深色)', await page.evaluate(() => document.querySelector('#tpMode button[data-mode="dark"]').classList.contains('on')));

// 3) 切浅色
const bgDark = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--bg').trim());
await page.click('#tpMode button[data-mode="light"]'); await page.waitForTimeout(400);
const bgLight = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--bg').trim());
ok('切浅色 → data-mode=light', await page.evaluate(() => document.documentElement.dataset.mode === 'light'));
ok('--bg 变化', bgDark !== bgLight, bgDark + ' -> ' + bgLight);
ok('theming 类已移除', await page.evaluate(() => !document.documentElement.classList.contains('theming')));

// 4) 强调色切换（浅色下的靛蓝）
await page.click('#tpAcc button[data-accent="indigo"]'); await page.waitForTimeout(400);
ok('强调色=靛蓝', await page.evaluate(() => document.documentElement.dataset.accent === 'indigo'));
const accNow = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--acc').trim());
ok('--acc 已变=#5a6cb0', accNow.toLowerCase() === '#5a6cb0', accNow);

// 5) 自定义强调色
await page.evaluate(() => {
  const el = document.querySelector('#tpColor');
  el.value = '#c94f8a';
  el.dispatchEvent(new Event('input', { bubbles: true }));
});
await page.waitForTimeout(400);
const accCustom = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--acc').trim());
ok('自定义强调色生效', accCustom.toLowerCase() === '#c94f8a', accCustom);
ok('data-accent=custom', await page.evaluate(() => document.documentElement.dataset.accent === 'custom'));

// 6) 持久化（重载后保留 light + custom）
await page.reload({ waitUntil: 'domcontentloaded' });
await page.waitForTimeout(900);
ok('重载后保留浅色', await page.evaluate(() => document.documentElement.dataset.mode === 'light'));
ok('重载后保留自定义色', await page.evaluate(() => document.documentElement.dataset.accent === 'custom' && getComputedStyle(document.documentElement).getPropertyValue('--acc').trim().toLowerCase() === '#c94f8a'));

// 7) 跟随系统（模拟系统深浅）
await page.evaluate(() => { document.querySelector('#setMode button[data-mode="system"]').click(); });
await page.waitForTimeout(300);
await page.emulateMedia({ colorScheme: 'dark' }); await page.waitForTimeout(300);
const sysDark = await page.evaluate(() => document.documentElement.dataset.mode);
await page.emulateMedia({ colorScheme: 'light' }); await page.waitForTimeout(300);
const sysLight = await page.evaluate(() => document.documentElement.dataset.mode);
ok('跟随系统: dark→' + sysDark, sysDark === 'dark');
ok('跟随系统: light→' + sysLight, sysLight === 'light');

// 8) 设置页控件同步
const synced = await page.evaluate(() => {
  return document.querySelector('#setMode button[data-mode="system"]').classList.contains('on')
      && document.querySelector('#setAcc button[data-accent="custom"]').classList.contains('on');
});
ok('设置页控件同步', synced);

// 9) 弹层互斥 + Esc
await page.click('#scenarioBtn'); await page.waitForTimeout(200);
ok('场景弹层打开', await page.isVisible('#scenarioPop'));
await page.click('#themeBtn'); await page.waitForTimeout(240);
ok('打开外观时关闭场景弹层', await page.evaluate(() => !document.querySelector('#scenarioPop').classList.contains('on')));
await page.keyboard.press('Escape'); await page.waitForTimeout(200);
ok('Esc 关闭外观弹层', await page.evaluate(() => !document.querySelector('#themePop').classList.contains('on')));

// 10) 还原默认（深色+鎏金），供后续截图一致性
await page.evaluate(() => {
  localStorage.removeItem('ayt.theme');
});
await page.reload({ waitUntil: 'domcontentloaded' }); await page.waitForTimeout(600);
ok('清 localStorage 后回默认深色', await page.evaluate(() => document.documentElement.dataset.mode === 'dark' && document.documentElement.dataset.accent === 'brass'));

console.log(results.join('\n'));
const fails = results.filter(r => r.startsWith('FAIL')).length;
console.log('===== RESULT: ' + (fails ? fails + ' FAIL' : 'ALL PASS') + ' =====');
await browser.close();
process.exit(fails ? 1 : 0);
