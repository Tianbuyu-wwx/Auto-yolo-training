// v7 玻璃皮肤下的参数弹窗截图
import { createRequire } from 'module';
const require = createRequire('C:/Users/Tianbuyu/AppData/Local/hermes/skills/creative/ui-craft-studio/package.json');
const { chromium } = require('playwright');
const URL = 'file:///E:/%E9%A1%B9%E7%9B%AE/Auto-yolo-training/launcher-design/AYT-Launcher-v7.html?page=config#';
const OUT = 'E:/项目/Auto-yolo-training/launcher-design/_selfcheck/';

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1560, height: 940 }, deviceScaleFactor: 2 });
const page = await ctx.newPage();
await page.addInitScript(() => localStorage.setItem('ayt.skin', 'glass'));
await page.goto(URL + '?t=' + Date.now(), { waitUntil: 'domcontentloaded' });
await page.evaluate(() => Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 3000))]));
await page.waitForTimeout(700);
await page.click('#recipeOpen'); await page.waitForTimeout(700);
await (await page.$('#stageInner')).screenshot({ path: OUT + 'v7-modal-glass.png' });
console.log('shot -> v7-modal-glass');
await browser.close();
