// 浅色全套 + 主题展示 截图（2x，#stageInner 元素截图）
// 运行：复制到 ui-craft-studio skill 目录后：
//   cd <skill目录> && CHROME_PATH="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" node make-shots.mjs
import { chromium } from 'playwright';
const URL = 'file:///E:/%E9%A1%B9%E7%9B%AE/Auto-yolo-training/tools/launcher-design/AYT-Launcher-v1.html';
const OUT = 'E:/项目/Auto-yolo-training/tools/launcher-design/_selfcheck/';
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, headless: true });

async function shot(name, theme, suffix, setup) {
  const ctx = await browser.newContext({ viewport: { width: 1560, height: 940 }, deviceScaleFactor: 2 });
  if (theme) await ctx.addInitScript(t => localStorage.setItem('ayt.theme', JSON.stringify(t)), theme);
  const page = await ctx.newPage();
  await page.goto(URL + '?t=' + Date.now() + (suffix || ''), { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 3500))]));
  await page.waitForTimeout(600);
  if (setup) await setup(page);
  await page.waitForTimeout(900);
  const el = await page.$('#stageInner');
  await el.screenshot({ path: OUT + name + '.png' });
  await ctx.close();
  console.log('shot ->', name);
}

const LIGHT = { mode: 'light', accent: 'brass' };
const CELADON = { mode: 'dark', accent: 'celadon' };
const CUSTOM = { mode: 'dark', accent: 'custom', custom: '#c96f4a' };

// —— 浅色全套（10 屏）——
await shot('light-home', LIGHT, '');
await shot('light-services', LIGHT, '#services');
await shot('light-env', LIGHT, '#env');
await shot('light-assets', LIGHT, '#assets');
await shot('light-settings', LIGHT, '#settings');
await shot('light-scene-training', LIGHT, '?scene=training#');
await shot('light-scene-portbusy', LIGHT, '?scene=portbusy#');
await shot('light-scene-firstrun', LIGHT, '?scene=firstrun#', async () => { await new Promise(r => setTimeout(r, 2600)); });
await shot('light-scene-empty', LIGHT, '?scene=empty#');
await shot('light-weights', LIGHT, '#assets', async (p) => { await p.click('#assetSeg button[data-tab="weights"]'); });

// —— 主题展示 ——
await shot('showcase-popover', null, '', async (p) => { await p.click('#themeBtn'); });
await shot('showcase-celadon', CELADON, '');
await shot('showcase-custom', CUSTOM, '');
await shot('showcase-light-settings', LIGHT, '#settings');

console.log('ALL SHOTS DONE');
await browser.close();
